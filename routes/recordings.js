const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const OpenAI = require('openai');
const { auth, requireRole } = require('../middleware/auth');
const { query, run } = require('../config/database');

const router = express.Router();

// Configure OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

// Configure multer for audio file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadDir = 'uploads/';
    if (!fs.existsSync(uploadDir)) {
      fs.mkdirSync(uploadDir, { recursive: true });
    }
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, 'recording-' + uniqueSuffix + path.extname(file.originalname));
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 50 * 1024 * 1024 }, // 50MB limit
  fileFilter: (req, file, cb) => {
    const allowedTypes = /audio\/(mp3|wav|m4a|aac|ogg|webm|mp4)/;
    if (allowedTypes.test(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Only audio files are allowed'));
    }
  }
});

// Upload new recording
router.post('/upload', auth, requireRole(['emt']), upload.single('audio'), async (req, res) => {
  try {
    const { patient_info } = req.body;
    const audio_file_path = req.file.path;
    const emt_id = req.user.id;

    // Create recording record
    const result = await run(
      'INSERT INTO recordings (emt_id, patient_info, audio_file_path) VALUES (?, ?, ?)',
      [emt_id, patient_info, audio_file_path]
    );

    // Process recording asynchronously
    processRecording(result.id, audio_file_path);

    res.status(201).json({
      message: 'Recording uploaded successfully',
      recording: { id: result.id, emt_id, patient_info, audio_file_path }
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: 'Server error during upload' });
  }
});

// Get all recordings for EMT
router.get('/my-recordings', auth, requireRole(['emt']), async (req, res) => {
  try {
    const recordings = await query(
      'SELECT * FROM recordings WHERE emt_id = ? ORDER BY created_at DESC',
      [req.user.id]
    );

    res.json(recordings);
  } catch (error) {
    console.error('Get recordings error:', error);
    res.status(500).json({ error: 'Server error getting recordings' });
  }
});

// Get recording by ID
router.get('/:id', auth, async (req, res) => {
  try {
    const recordings = await query(
      'SELECT r.*, u.first_name as emt_first_name, u.last_name as emt_last_name FROM recordings r JOIN users u ON r.emt_id = u.id WHERE r.id = ?',
      [req.params.id]
    );

    if (recordings.length === 0) {
      return res.status(404).json({ error: 'Recording not found' });
    }

    res.json(recordings[0]);
  } catch (error) {
    console.error('Get recording error:', error);
    res.status(500).json({ error: 'Server error getting recording' });
  }
});

// Process recording function (transcription + LLM analysis)
async function processRecording(recordingId, audioFilePath) {
  try {
    // Update status to processing
    await run(
      'UPDATE recordings SET status = ? WHERE id = ?',
      ['processing', recordingId]
    );

    // Step 1: Get patient information from database
    const recording = await query(
      'SELECT patient_info FROM recordings WHERE id = ?',
      [recordingId]
    );
    
    const patientInfo = recording[0]?.patient_info || '';

    // Step 2: Transcribe audio using OpenAI Whisper
    const transcription = await transcribeAudio(audioFilePath);
    
    // Step 3: Analyze with LLM (including both transcription and patient info)
    const analysis = await analyzeWithLLM(transcription, patientInfo);
    
    // Step 4: Update recording with structured results
    await run(
      `UPDATE recordings SET 
        transcription = ?, 
        llm_summary = ?, 
        risk_score = ?, 
        priority_level = ?, 
        chief_complaint = ?, 
        vital_signs = ?, 
        symptoms = ?, 
        recommended_actions = ?, 
        critical_info = ?,
        status = ? 
      WHERE id = ?`,
      [
        transcription, 
        analysis.medical_summary || JSON.stringify(analysis),
        analysis.risk_score || 5,
        analysis.priority_level || 3,
        analysis.chief_complaint || 'Not specified',
        analysis.vital_signs || 'Not recorded',
        analysis.symptoms || 'Not specified',
        analysis.recommended_actions || 'Standard care',
        analysis.critical_info || 'None',
        'completed', 
        recordingId
      ]
    );

    // Step 5: Notify appropriate doctors
    await notifyDoctors(recordingId, analysis.medical_summary || JSON.stringify(analysis));

  } catch (error) {
    console.error('Processing error:', error);
    await run(
      'UPDATE recordings SET status = ? WHERE id = ?',
      ['error', recordingId]
    );
  }
}

// Transcribe audio using OpenAI Whisper
async function transcribeAudio(audioFilePath) {
  try {
    const audioFile = fs.createReadStream(audioFilePath);
    const transcription = await openai.audio.transcriptions.create({
      file: audioFile,
      model: "whisper-1",
      response_format: "text"
    });
    return transcription;
  } catch (error) {
    console.error('Transcription error:', error);
    throw error;
  }
}

// Analyze transcription with LLM
async function analyzeWithLLM(transcription, patientInfo = '') {
  try {
    const prompt = `You are an emergency medicine AI specialist. Analyze this EMT conversation and patient information to provide a comprehensive medical assessment.

AUDIO TRANSCRIPTION: ${transcription}

ADDITIONAL PATIENT INFORMATION: ${patientInfo}

Analyze BOTH the audio conversation AND the typed patient information to provide a complete medical assessment.

Return ONLY this JSON structure (no other text):
{
  "chief_complaint": "Brief description of the patient's main complaint",
  "vital_signs": "Any vital signs mentioned (BP, HR, RR, Temp, O2 Sat, etc.)",
  "symptoms": "Key symptoms observed or reported",
  "risk_score": 5,
  "priority_level": 3,
  "urgency_level": "urgent",
  "recommended_actions": "Specific medical actions recommended",
  "critical_info": "Critical information for doctors",
  "medical_summary": "Comprehensive medical summary"
}

RISK SCORING GUIDELINES (be precise):
- Risk 9-10: Multiple severe traumas, cardiac arrest, severe bleeding, unconscious/unresponsive
- Risk 7-8: Single severe trauma (major car accident with multiple injuries), severe head injury, chest trauma
- Risk 5-6: Moderate trauma (broken bones, moderate injuries), stable but injured patients
- Risk 3-4: Minor injuries (cuts, bruises, minor fractures), stable patients with minor complaints
- Risk 1-2: Very minor issues (heartburn, minor cuts), routine care patients

PRIORITY LEVEL GUIDELINES:
- Priority 1: Critical (risk 9-10)
- Priority 2: High (risk 7-8) 
- Priority 3: Medium (risk 5-6)
- Priority 4: Low (risk 3-4)
- Priority 5: Routine (risk 1-2)

URGENCY LEVELS:
- "critical": Risk 9-10
- "urgent": Risk 7-8
- "moderate": Risk 5-6
- "low": Risk 3-4
- "routine": Risk 1-2

EXAMPLES:
- "Patient dying, fell from bridge, then run over by car" = Risk 9-10
- "Major car accident, multiple injuries, unconscious" = Risk 7-8
- "Car accident, broken arm, stable vital signs" = Risk 5-6
- "Minor car accident, cuts and bruises" = Risk 3-4
- "Heartburn, feeling fine" = Risk 1-2

Return ONLY the JSON object with no additional text.`;

    const response = await openai.chat.completions.create({
      model: "gpt-4",
      messages: [{ role: "user", content: prompt }],
      temperature: 0.3,
      max_tokens: 1000
    });

    const aiResponse = response.choices[0].message.content.trim();
    console.log('Raw AI response:', aiResponse);

    // Clean the response to extract JSON
    let cleanedResponse = aiResponse;
    if (aiResponse.includes('```json')) {
      cleanedResponse = aiResponse.split('```json')[1].split('```')[0].trim();
    } else if (aiResponse.includes('```')) {
      cleanedResponse = aiResponse.split('```')[1].split('```')[0].trim();
    }

    const result = JSON.parse(cleanedResponse);
    console.log('Cleaned AI response:', result);
    return result;

  } catch (error) {
    console.error('LLM analysis error:', error);
    // Return default values if AI analysis fails
    return {
      chief_complaint: "Unable to analyze",
      vital_signs: "Not available",
      symptoms: "Not specified",
      risk_score: 5,
      priority_level: 3,
      urgency_level: "moderate",
      recommended_actions: "Manual review required",
      critical_info: "AI analysis failed",
      medical_summary: "Unable to generate medical summary"
    };
  }
}

// Notify appropriate doctors
async function notifyDoctors(recordingId, summary) {
  try {
    // Get available doctors
    const doctors = await query(
      'SELECT * FROM users WHERE role = ? AND is_available = ?',
      ['doctor', 1]
    );

    // For now, notify all available doctors
    // In production, you'd implement specialty matching
    for (const doctor of doctors) {
      await run(
        'INSERT INTO notifications (recording_id, doctor_id, notification_type) VALUES (?, ?, ?)',
        [recordingId, doctor.id, 'both']
      );
    }

    // Update recording status
    await run(
      'UPDATE recordings SET status = ? WHERE id = ?',
      ['notified', recordingId]
    );

  } catch (error) {
    console.error('Notification error:', error);
    throw error;
  }
}

module.exports = router; 