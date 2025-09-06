-- Create database schema for Shealthcare EMT System

-- Users table (EMTs and Doctors)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('emt', 'doctor')),
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    specialty VARCHAR(100), -- For doctors
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recordings table
CREATE TABLE IF NOT EXISTS recordings (
    id SERIAL PRIMARY KEY,
    emt_id INTEGER REFERENCES users(id),
    patient_info TEXT,
    audio_file_path VARCHAR(255) NOT NULL,
    transcription TEXT,
    llm_summary TEXT,
    urgency_level VARCHAR(20) DEFAULT 'medium' CHECK (urgency_level IN ('low', 'medium', 'high', 'critical')),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'notified')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    recording_id INTEGER REFERENCES recordings(id),
    doctor_id INTEGER REFERENCES users(id),
    notification_type VARCHAR(20) NOT NULL CHECK (notification_type IN ('sms', 'email', 'both')),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered BOOLEAN DEFAULT false,
    read_at TIMESTAMP,
    response TEXT
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_recordings_emt_id ON recordings(emt_id);
CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
CREATE INDEX IF NOT EXISTS idx_notifications_doctor_id ON notifications(doctor_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_available ON users(is_available);

-- Insert sample data for testing
INSERT INTO users (username, email, password_hash, role, first_name, last_name, phone, specialty) VALUES
('dr.smith', 'dr.smith@hospital.com', '$2a$10$dummyhash', 'doctor', 'John', 'Smith', '+1234567890', 'Emergency Medicine'),
('dr.jones', 'dr.jones@hospital.com', '$2a$10$dummyhash', 'doctor', 'Sarah', 'Jones', '+1234567891', 'Cardiology'),
('emt.wilson', 'emt.wilson@ems.com', '$2a$10$dummyhash', 'emt', 'Mike', 'Wilson', '+1234567892', NULL),
('emt.garcia', 'emt.garcia@ems.com', '$2a$10$dummyhash', 'emt', 'Maria', 'Garcia', '+1234567893', NULL)
ON CONFLICT (username) DO NOTHING; 