const express = require('express');
const { auth, requireRole } = require('../middleware/auth');
const { query, run } = require('../config/database');

const router = express.Router();

// Get all available doctors
router.get('/available', async (req, res) => {
  try {
    const doctors = await query(
      'SELECT id, first_name, last_name, specialty, phone, email FROM users WHERE role = ? AND is_available = ?',
      ['doctor', 1]
    );

    res.json(doctors);
  } catch (error) {
    console.error('Get doctors error:', error);
    res.status(500).json({ error: 'Server error getting doctors' });
  }
});

// Get doctor's notifications with filtering
router.get('/notifications', auth, requireRole(['doctor']), async (req, res) => {
  try {
    const { sortBy = 'newest' } = req.query;
    
    let orderClause = '';
    switch (sortBy) {
      case 'newest':
        orderClause = 'ORDER BY n.sent_at DESC';
        break;
      case 'priority':
        orderClause = 'ORDER BY r.risk_score DESC, r.priority_level ASC, n.sent_at DESC';
        break;
      case 'oldest':
        orderClause = 'ORDER BY n.sent_at ASC';
        break;
      default:
        orderClause = 'ORDER BY n.sent_at DESC';
    }

    const notifications = await query(
      `SELECT n.*, r.patient_info, r.llm_summary, r.urgency_level, r.risk_score, r.priority_level, 
              r.chief_complaint, r.vital_signs, r.symptoms, r.recommended_actions, r.critical_info,
              r.created_at as recording_time, u.first_name as emt_first_name, u.last_name as emt_last_name
       FROM notifications n
       JOIN recordings r ON n.recording_id = r.id
       JOIN users u ON r.emt_id = u.id
       WHERE n.doctor_id = ?
       ${orderClause}`,
      [req.user.id]
    );

    res.json(notifications);
  } catch (error) {
    console.error('Get notifications error:', error);
    res.status(500).json({ error: 'Server error getting notifications' });
  }
});

// Get specific recording details
router.get('/recording/:id', auth, requireRole(['doctor']), async (req, res) => {
  try {
    const recordings = await query(
      `SELECT r.*, u.first_name as emt_first_name, u.last_name as emt_last_name
       FROM recordings r
       JOIN users u ON r.emt_id = u.id
       WHERE r.id = ?`,
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

// Update doctor availability
router.patch('/availability', auth, requireRole(['doctor']), async (req, res) => {
  try {
    const { is_available } = req.body;
    
    await run(
      'UPDATE users SET is_available = ? WHERE id = ?',
      [is_available ? 1 : 0, req.user.id]
    );

    res.json({ message: 'Availability updated successfully', is_available });
  } catch (error) {
    console.error('Update availability error:', error);
    res.status(500).json({ error: 'Server error updating availability' });
  }
});

// Mark notification as read
router.patch('/notifications/:id/read', auth, requireRole(['doctor']), async (req, res) => {
  try {
    await run(
      'UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ? AND doctor_id = ?',
      [req.params.id, req.user.id]
    );

    res.json({ message: 'Notification marked as read' });
  } catch (error) {
    console.error('Mark read error:', error);
    res.status(500).json({ error: 'Server error marking notification as read' });
  }
});

// Respond to a recording
router.post('/recordings/:id/respond', auth, requireRole(['doctor']), async (req, res) => {
  try {
    const { response } = req.body;
    
    await run(
      'UPDATE notifications SET response = ? WHERE recording_id = ? AND doctor_id = ?',
      [response, req.params.id, req.user.id]
    );

    res.json({ message: 'Response recorded successfully' });
  } catch (error) {
    console.error('Response error:', error);
    res.status(500).json({ error: 'Server error recording response' });
  }
});

module.exports = router; 