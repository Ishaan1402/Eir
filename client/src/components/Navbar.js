import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, User, Shield } from 'lucide-react';

const Navbar = () => {
  const { user, logout } = useAuth();

  return (
    <nav className="bg-white shadow-lg border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <h1 className="text-2xl font-bold text-red-600">
                🏥 Asclepius
              </h1>
            </div>
            <div className="ml-6 flex items-center space-x-4">
              <span className="text-gray-700 font-medium">
                {user?.role === 'emt' ? 'EMT Dashboard' : 'Doctor Dashboard'}
              </span>
            </div>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-gray-700">
              {user?.role === 'doctor' && (
                <Shield className="h-5 w-5 text-blue-600" />
              )}
              <User className="h-5 w-5 text-gray-600" />
              <span className="font-medium">
                {user?.first_name} {user?.last_name}
              </span>
              <span className="text-sm text-gray-500">
                ({user?.role?.toUpperCase()})
              </span>
            </div>
            
            <button
              onClick={logout}
              className="flex items-center space-x-2 px-4 py-2 text-gray-700 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            >
              <LogOut className="h-5 w-5" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar; 