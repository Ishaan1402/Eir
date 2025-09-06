#!/bin/bash

echo "🚑 Starting Shealthcare EMT System (SQLite Version)..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please copy env.example to .env and configure your API keys"
    exit 1
fi

# Install backend dependencies
echo "📦 Installing backend dependencies..."
npm install

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd client && npm install && cd ..

# Create uploads directory
echo "📁 Creating uploads directory..."
mkdir -p uploads

echo "✅ Dependencies installed successfully!"
echo ""
echo "🚀 To start the system:"
echo "1. Backend: npm run dev (in main directory)"
echo "2. Frontend: cd client && npm start"
echo ""
echo "🌐 The app will be available at:"
echo "   Frontend: http://localhost:3000"
echo "   Backend: http://localhost:5000"
echo ""
echo "📱 Demo accounts available on the login page"
echo "💾 SQLite database will be created automatically at: shealthcare.db" 