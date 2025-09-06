const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const bcrypt = require('bcryptjs');

// Create database file in the project root
const dbPath = path.join(__dirname, '..', 'asclepius.db');

const db = new sqlite3.Database(dbPath, (err) => {
  if (err) {
    console.error('❌ Database connection failed:', err.message);
  } else {
    console.log('✅ SQLite database connected successfully');
    console.log('📁 Database file:', dbPath);
    initDatabase();
  }
});

// Initialize database tables
function initDatabase() {
  const schema = `
    -- Users table (EMTs and Doctors)
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK (role IN ('emt', 'doctor')),
      first_name TEXT NOT NULL,
      last_name TEXT NOT NULL,
      phone TEXT,
      specialty TEXT,
      is_available BOOLEAN DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Recordings table
    CREATE TABLE IF NOT EXISTS recordings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      emt_id INTEGER,
      patient_info TEXT,
      audio_file_path TEXT NOT NULL,
      transcription TEXT,
      llm_summary TEXT,
      urgency_level TEXT DEFAULT 'medium' CHECK (urgency_level IN ('low', 'medium', 'high', 'critical')),
      risk_score INTEGER DEFAULT 5 CHECK (risk_score >= 0 AND risk_score <= 10),
      priority_level INTEGER DEFAULT 3 CHECK (priority_level >= 1 AND priority_level <= 5),
      chief_complaint TEXT,
      vital_signs TEXT,
      symptoms TEXT,
      recommended_actions TEXT,
      critical_info TEXT,
      status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'notified', 'error')),
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (emt_id) REFERENCES users (id)
    );

    -- Notifications table
    CREATE TABLE IF NOT EXISTS notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      recording_id INTEGER,
      doctor_id INTEGER,
      notification_type TEXT NOT NULL CHECK (notification_type IN ('sms', 'email', 'both')),
      sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      delivered BOOLEAN DEFAULT 0,
      read_at DATETIME,
      response TEXT,
      FOREIGN KEY (recording_id) REFERENCES recordings (id),
      FOREIGN KEY (doctor_id) REFERENCES users (id)
    );

    -- Create indexes for better performance
    CREATE INDEX IF NOT EXISTS idx_recordings_emt_id ON recordings(emt_id);
    CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
    CREATE INDEX IF NOT EXISTS idx_notifications_doctor_id ON notifications(doctor_id);
    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
    CREATE INDEX IF NOT EXISTS idx_users_available ON users(is_available);
  `;

  db.exec(schema, (err) => {
    if (err) {
      console.error('❌ Schema creation failed:', err.message);
    } else {
      console.log('✅ Database schema created successfully');
      insertSampleData();
    }
  });
}

// Insert sample data with proper password hashes
async function insertSampleData() {
  try {
    // Hash the password "password123" for all demo accounts
    const passwordHash = await bcrypt.hash('password123', 10);
    
    const sampleUsers = [
      ['dr.smith', 'dr.smith@hospital.com', passwordHash, 'doctor', 'John', 'Smith', '+1234567890', 'Emergency Medicine'],
      ['dr.jones', 'dr.jones@hospital.com', passwordHash, 'doctor', 'Sarah', 'Jones', '+1234567891', 'Cardiology'],
      ['emt.wilson', 'emt.wilson@ems.com', passwordHash, 'emt', 'Mike', 'Wilson', '+1234567892', null],
      ['emt.garcia', 'emt.garcia@ems.com', passwordHash, 'emt', 'Maria', 'Garcia', '+1234567893', null]
    ];

    const insertUser = db.prepare('INSERT OR IGNORE INTO users (username, email, password_hash, role, first_name, last_name, phone, specialty) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    
    sampleUsers.forEach(user => {
      insertUser.run(user);
    });
    
    insertUser.finalize(() => {
      console.log('✅ Sample data inserted successfully with proper passwords');
      console.log('🔑 Demo accounts all use password: password123');
    });
    
  } catch (error) {
    console.error('❌ Error creating sample data:', error);
  }
}

// Helper function to run queries with promises
function query(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) {
        reject(err);
      } else {
        resolve(rows);
      }
    });
  });
}

// Helper function to run single queries
function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function(err) {
      if (err) {
        reject(err);
      } else {
        resolve({ id: this.lastID, changes: this.changes });
      }
    });
  });
}

module.exports = { db, query, run }; 