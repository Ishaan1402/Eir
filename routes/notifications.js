const express = require('express');
const twilio = require('twilio');
const sgMail = require('@sendgrid/mail');
const { auth, requireRole } = require('../middleware/auth');
const { query, run } = require('../config/database');

const router = express.Router();

// Configure Twilio
const twilioClient = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

// Configure SendGrid
sgMail.setApiKey(process.env.SENDGRID_API_KEY);

// Send notification to doctor
router.post('/send', auth, requireRole(['emt']), async (req, res) => {
  try {
    const { recording_id, doctor_id, notification_type } = req.body;
    
    // Get recording and doctor details
    const recordings = await query(
      'SELECT * FROM recordings WHERE id = ?',
      [recording_id]
    );
    
    const doctors = await query(
      'SELECT * FROM users WHERE id = ?',
      [doctor_id]
    );
    
    if (recordings.length === 0 || doctors.length === 0) {
      return res.status(404).json({ error: 'Recording or doctor not found' });
    }
    
    const recordingData = recordings[0];
    const doctorData = doctors[0];
    
    // Send notifications based on type
    if (notification_type === 'sms' || notification_type === 'both') {
      await sendSMS(doctorData.phone, recordingData, doctorData);
    }
    
    if (notification_type === 'email' || notification_type === 'both') {
      await sendEmail(doctorData.email, recordingData, doctorData);
    }
    
    // Update notification record
    await run(
      'UPDATE notifications SET delivered = 1 WHERE recording_id = ? AND doctor_id = ?',
      [recording_id, doctor_id]
    );
    
    res.json({ message: 'Notification sent successfully' });
    
  } catch (error) {
    console.error('Send notification error:', error);
    res.status(500).json({ error: 'Server error sending notification' });
  }
});

// Send SMS notification
async function sendSMS(phoneNumber, recording, doctor) {
  try {
    const message = `🚑 EMERGENCY ALERT - Dr. ${doctor.last_name}

Patient Summary: ${recording.llm_summary?.substring(0, 100)}...

Urgency: ${recording.urgency_level}
EMT: ${recording.emt_first_name} ${recording.emt_last_name}

View full details at: ${process.env.FRONTEND_URL || 'http://localhost:3000'}/recording/${recording.id}

Reply STOP to unsubscribe`;

    await twilioClient.messages.create({
      body: message,
      from: process.env.TWILIO_PHONE_NUMBER,
      to: phoneNumber
    });
    
    console.log(`SMS sent to ${phoneNumber}`);
    
  } catch (error) {
    console.error('SMS error:', error);
    throw error;
  }
}

// Send email notification
async function sendEmail(email, recording, doctor) {
  try {
    const emailContent = {
      to: email,
      from: process.env.SENDGRID_FROM_EMAIL,
      subject: `🚑 Emergency Alert - Patient Summary for Dr. ${doctor.last_name}`,
      html: `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #d32f2f;">🚑 EMERGENCY ALERT</h2>
          
          <div style="background-color: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3>Patient Summary</h3>
            <p style="white-space: pre-wrap;">${recording.llm_summary || 'Summary not available'}</p>
          </div>
          
          <div style="margin: 20px 0;">
            <p><strong>Urgency Level:</strong> <span style="color: ${getUrgencyColor(recording.urgency_level)};">${recording.urgency_level?.toUpperCase()}</span></p>
            <p><strong>EMT:</strong> ${recording.emt_first_name} ${recording.emt_last_name}</p>
            <p><strong>Time:</strong> ${new Date(recording.created_at).toLocaleString()}</p>
          </div>
          
          <div style="text-align: center; margin: 30px 0;">
            <a href="${process.env.FRONTEND_URL || 'http://localhost:3000'}/recording/${recording.id}" 
               style="background-color: #1976d2; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
              View Full Details
            </a>
          </div>
          
          <hr style="margin: 30px 0;">
          <p style="color: #666; font-size: 12px;">
            This is an automated notification from the Shealthcare EMT System.
            Please do not reply to this email.
          </p>
        </div>
      `
    };
    
    await sgMail.send(emailContent);
    console.log(`Email sent to ${email}`);
    
  } catch (error) {
    console.error('Email error:', error);
    throw error;
  }
}

// Get urgency color for email styling
function getUrgencyColor(urgency) {
  switch (urgency) {
    case 'critical': return '#d32f2f';
    case 'high': return '#f57c00';
    case 'medium': return '#fbc02d';
    case 'low': return '#388e3c';
    default: return '#666';
  }
}

// Get notification status
router.get('/status/:id', auth, async (req, res) => {
  try {
    const notifications = await query(
      'SELECT * FROM notifications WHERE id = ?',
      [req.params.id]
    );
    
    if (notifications.length === 0) {
      return res.status(404).json({ error: 'Notification not found' });
    }
    
    res.json(notifications[0]);
    
  } catch (error) {
    console.error('Get notification status error:', error);
    res.status(500).json({ error: 'Server error getting notification status' });
  }
});

// Test notification endpoint (for development)
router.post('/test', auth, requireRole(['emt']), async (req, res) => {
  try {
    const { phone, email } = req.body;
    
    if (phone) {
      await sendSMS(phone, {
        llm_summary: 'This is a test notification from the Shealthcare EMT System.',
        urgency_level: 'medium',
        emt_first_name: 'Test',
        emt_last_name: 'EMT',
        id: 'test-123'
      }, {
        last_name: 'Test',
        phone: phone
      });
    }
    
    if (email) {
      await sendEmail(email, {
        llm_summary: 'This is a test notification from the Shealthcare EMT System.',
        urgency_level: 'medium',
        emt_first_name: 'Test',
        emt_last_name: 'EMT',
        id: 'test-123',
        created_at: new Date()
      }, {
        last_name: 'Test',
        email: email
      });
    }
    
    res.json({ message: 'Test notification sent successfully' });
    
  } catch (error) {
    console.error('Test notification error:', error);
    res.status(500).json({ error: 'Server error sending test notification' });
  }
});

module.exports = router; 