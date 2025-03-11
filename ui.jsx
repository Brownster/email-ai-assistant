import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Inbox, Mail, Send, Archive, Trash, Search, Filter, 
         ChevronDown, ChevronUp, Edit, Save, X, Check, RefreshCw } from 'lucide-react';

// Create API service
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:3001/api/v1';

const emailService = {
  getEmails: async (filter = 'pending_review', sortBy = 'received_timestamp', sortOrder = 'desc', searchTerm = '') => {
    try {
      const response = await axios.get(`${API_BASE_URL}/emails`, {
        params: { status: filter, sortBy, sortOrder, search: searchTerm }
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching emails:', error);
      throw error;
    }
  },
  
  getEmailById: async (emailId) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/emails/${emailId}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching email ${emailId}:`, error);
      throw error;
    }
  },
  
  updateEmailStatus: async (emailId, status) => {
    try {
      const response = await axios.patch(`${API_BASE_URL}/emails/${emailId}/status`, { status });
      return response.data;
    } catch (error) {
      console.error(`Error updating email ${emailId} status:`, error);
      throw error;
    }
  },
  
  updateDraftReply: async (emailId, draftId, content) => {
    try {
      const response = await axios.put(`${API_BASE_URL}/drafts/${draftId}`, { 
        body_text: content,
        is_edited: true
      });
      return response.data;
    } catch (error) {
      console.error(`Error updating draft ${draftId}:`, error);
      throw error;
    }
  },
  
  sendReply: async (emailId, draftId) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/emails/${emailId}/send`, { draftId });
      return response.data;
    } catch (error) {
      console.error(`Error sending reply for email ${emailId}:`, error);
      throw error;
    }
  }
};

const EmailManagementDashboard = () => {
  // State for emails, selected email, and UI controls
  const [emails, setEmails] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [replyContent, setReplyContent] = useState('');
  const [editingReply, setEditingReply] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('pending_review');
  const [sortBy, setSortBy] = useState('received_timestamp');
  const [sortOrder, setSortOrder] = useState('desc');
  const [searchTerm, setSearchTerm] = useState('');

  // Fetch emails based on current filters
  const fetchEmails = async () => {
    setLoading(true);
    try {
      const data = await emailService.getEmails(filter, sortBy, sortOrder, searchTerm);
      setEmails(data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch emails. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Load emails when component mounts or filters change
  useEffect(() => {
    fetchEmails();
  }, [filter, sortBy, sortOrder, searchTerm]);

  const handleSelectEmail = async (emailId) => {
    setLoading(true);
    try {
      const emailData = await emailService.getEmailById(emailId);
      setSelectedEmail(emailData);
      
      // Get the latest draft reply
      if (emailData.draft_replies && emailData.draft_replies.length > 0) {
        const latestDraft = emailData.draft_replies[0]; // Assuming sorted by date
        setSelectedDraft(latestDraft);
        setReplyContent(latestDraft.body_text);
      } else {
        setSelectedDraft(null);
        setReplyContent('');
      }
      
      setEditingReply(false);
      setError(null);
    } catch (err) {
      setError('Failed to load email details. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleEditReply = () => {
    setEditingReply(true);
  };

  const handleSaveReply = async () => {
    if (selectedEmail && selectedDraft) {
      setLoading(true);
      try {
        const updatedDraft = await emailService.updateDraftReply(
          selectedEmail.email_id, 
          selectedDraft.draft_id, 
          replyContent
        );
        
        // Update the selected draft with new content
        setSelectedDraft(updatedDraft);
        setEditingReply(false);
        setError(null);
      } catch (err) {
        setError('Failed to save draft reply. Please try again.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleSendReply = async () => {
    if (selectedEmail && selectedDraft) {
      setLoading(true);
      try {
        await emailService.sendReply(selectedEmail.email_id, selectedDraft.draft_id);
        
        // Update email status locally
        const updatedEmail = { ...selectedEmail, status: 'sent' };
        setSelectedEmail(updatedEmail);
        
        // Update email in list
        setEmails(emails.map(email => 
          email.email_id === selectedEmail.email_id 
            ? updatedEmail 
            : email
        ));
        
        setError(null);
        // Show success toast or notification
        alert("Email sent successfully!");
      } catch (err) {
        setError('Failed to send email. Please try again.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleRefresh = () => {
    fetchEmails();
  };

  const handleStatusChange = async (emailId, newStatus) => {
    setLoading(true);
    try {
      const updatedEmail = await emailService.updateEmailStatus(emailId, newStatus);
      
      // Update email in list
      setEmails(emails.map(email => 
        email.email_id === emailId 
          ? updatedEmail 
          : email
      ));
      
      // Update selected email if it's the one being changed
      if (selectedEmail && selectedEmail.email_id === emailId) {
        setSelectedEmail(updatedEmail);
      }
      
      setError(null);
    } catch (err) {
      setError(`Failed to change email status to ${newStatus}. Please try again.`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSortOrder = () => {
    setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <div className="w-64 bg-gray-800 text-white p-4">
        <h1 className="text-xl font-bold mb-6">Email Management</h1>
        
        <div className="space-y-2">
          <button 
            className={`flex items-center space-x-2 w-full p-2 rounded ${filter === 'pending_review' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
            onClick={() => setFilter('pending_review')}
          >
            <Inbox size={18} />
            <span>Pending Review</span>
          </button>
          
          <button 
            className={`flex items-center space-x-2 w-full p-2 rounded ${filter === 'in_progress' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
            onClick={() => setFilter('in_progress')}
          >
            <Mail size={18} />
            <span>In Progress</span>
          </button>
          
          <button 
            className={`flex items-center space-x-2 w-full p-2 rounded ${filter === 'sent' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
            onClick={() => setFilter('sent')}
          >
            <Send size={18} />
            <span>Sent</span>
          </button>
          
          <button 
            className={`flex items-center space-x-2 w-full p-2 rounded ${filter === 'resolved' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
            onClick={() => setFilter('resolved')}
          >
            <Archive size={18} />
            <span>Resolved</span>
          </button>
          
          <button 
            className={`flex items-center space-x-2 w-full p-2 rounded ${filter === 'all' ? 'bg-blue-600' : 'hover:bg-gray-700'}`}
            onClick={() => setFilter('all')}
          >
            <Filter size={18} />
            <span>All Emails</span>
          </button>
        </div>
      </div>
      
      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Header with search */}
        <div className="bg-white p-4 shadow flex items-center justify-between">
          <div className="flex items-center w-1/2">
            <Search size={20} className="text-gray-400 mr-2" />
            <input
              type="text"
              placeholder="Search emails..."
              className="w-full p-2 border rounded"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              // Debounce search for better performance
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  fetchEmails();
                }
              }}
            />
          </div>
          
          <div className="flex items-center space-x-4">
            {error && <div className="text-red-500 text-sm">{error}</div>}
            <button 
              className="p-2 bg-blue-500 text-white rounded flex items-center space-x-1"
              onClick={handleRefresh}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
        
        {/* Email list and detail view */}
        <div className="flex-1 flex overflow-hidden">
          {/* Email list */}
          <div className="w-1/3 overflow-y-auto border-r">
            <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
              <h2 className="font-semibold">Emails ({emails.length})</h2>
              <button 
                className="flex items-center text-sm text-gray-600"
                onClick={toggleSortOrder}
              >
                Sort by date {sortOrder === 'asc' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>
            
            {loading && emails.length === 0 ? (
              <div className="flex justify-center items-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
              </div>
            ) : emails.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                No emails found
              </div>
            ) : (
              emails.map(email => (
                <div 
                  key={email.email_id}
                  className={`p-4 border-b cursor-pointer hover:bg-gray-50 ${selectedEmail?.email_id === email.email_id ? 'bg-blue-50' : ''}`}
                  onClick={() => handleSelectEmail(email.email_id)}
                >
                  <div className="flex justify-between items-start mb-1">
                    <div className="font-medium truncate flex-1">{email.from_name || email.from_address}</div>
                    <div className="text-xs text-gray-500">{formatDate(email.received_timestamp)}</div>
                  </div>
                  <div className="font-semibold mb-1 truncate">{email.subject}</div>
                  <div className="text-sm text-gray-600 truncate">{email.body_text?.split('\n')[0]}</div>
                  <div className="flex items-center mt-2">
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      email.status === 'pending_review' ? 'bg-yellow-100 text-yellow-800' : 
                      email.status === 'in_progress' ? 'bg-blue-100 text-blue-800' : 
                      email.status === 'resolved' ? 'bg-green-100 text-green-800' : 
                      email.status === 'sent' ? 'bg-purple-100 text-purple-800' : 
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {email.status.replace('_', ' ')}
                    </span>
                    <span className="text-xs ml-2 bg-gray-100 text-gray-800 px-2 py-1 rounded-full">
                      {email.mailbox_type}
                    </span>
                    {email.analysis?.categories && email.analysis.categories.length > 0 && (
                      <span className="text-xs ml-2 bg-indigo-100 text-indigo-800 px-2 py-1 rounded-full">
                        {email.analysis.categories[0]}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          
          {/* Email detail view */}
          <div className="flex-1 overflow-y-auto bg-white p-6">
            {selectedEmail ? (
              <div className="max-w-3xl mx-auto">
                <div className="mb-6">
                  <h1 className="text-2xl font-bold mb-2">{selectedEmail.subject}</h1>
                  <div className="flex justify-between mb-4">
                    <div>
                      <div><span className="font-semibold">From:</span> {selectedEmail.from_name || ''} {selectedEmail.from_address}</div>
                      <div><span className="font-semibold">To:</span> {selectedEmail.to_address}</div>
                      <div><span className="font-semibold">Date:</span> {formatDate(selectedEmail.received_timestamp)}</div>
                      {selectedEmail.analysis && (
                        <div className="mt-2">
                          <div><span className="font-semibold">Category:</span> {selectedEmail.analysis.categories?.join(', ')}</div>
                          {selectedEmail.analysis.sentiment && (
                            <div><span className="font-semibold">Sentiment:</span> {selectedEmail.analysis.sentiment}</div>
                          )}
                          {selectedEmail.analysis.urgency && (
                            <div><span className="font-semibold">Urgency:</span> {selectedEmail.analysis.urgency}/10</div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex space-x-2">
                      <button 
                        className={`px-3 py-1 rounded text-white ${selectedEmail.status === 'resolved' ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-500 hover:bg-green-600'}`}
                        disabled={selectedEmail.status === 'resolved'}
                        onClick={() => handleStatusChange(selectedEmail.email_id, 'resolved')}
                      >
                        Mark Resolved
                      </button>
                      <button 
                        className={`px-3 py-1 rounded text-white ${selectedEmail.status === 'in_progress' ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-500 hover:bg-blue-600'}`}
                        disabled={selectedEmail.status === 'in_progress'}
                        onClick={() => handleStatusChange(selectedEmail.email_id, 'in_progress')}
                      >
                        Mark In Progress
                      </button>
                    </div>
                  </div>
                </div>
                
                <div className="bg-gray-50 p-4 rounded-lg mb-6 whitespace-pre-wrap">
                  {selectedEmail.body_text}
                </div>
                
                {selectedEmail.analysis?.summary && (
                  <div className="mb-6">
                    <h2 className="text-lg font-semibold mb-2">Summary</h2>
                    <div className="bg-blue-50 p-4 rounded-lg">
                      {selectedEmail.analysis.summary}
                    </div>
                  </div>
                )}
                
                {selectedEmail.analysis?.required_info && selectedEmail.analysis.required_info.length > 0 && (
                  <div className="mb-6">
                    <h2 className="text-lg font-semibold mb-2">Required Information</h2>
                    <ul className="bg-yellow-50 p-4 rounded-lg list-disc pl-4">
                      {selectedEmail.analysis.required_info.map((info, index) => (
                        <li key={index}>{info}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {selectedDraft && (
                  <div className="border-t pt-6 mt-6">
                    <h2 className="text-lg font-semibold mb-3 flex items-center justify-between">
                      <span>
                        Draft Reply 
                        {selectedDraft.confidence && (
                          <span className="ml-2 text-sm bg-blue-100 text-blue-800 px-2 py-1 rounded">
                            Confidence: {(selectedDraft.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </span>
                      
                      <div className="flex space-x-2">
                        {editingReply ? (
                          <>
                            <button 
                              className="p-2 bg-green-500 text-white rounded flex items-center space-x-1"
                              onClick={handleSaveReply}
                            >
                              <Save size={16} />
                              <span>Save</span>
                            </button>
                            <button 
                              className="p-2 bg-gray-300 rounded flex items-center space-x-1"
                              onClick={() => {
                                setReplyContent(selectedDraft.body_text);
                                setEditingReply(false);
                              }}
                            >
                              <X size={16} />
                              <span>Cancel</span>
                            </button>
                          </>
                        ) : (
                          <button 
                            className="p-2 bg-blue-500 text-white rounded flex items-center space-x-1"
                            onClick={handleEditReply}
                          >
                            <Edit size={16} />
                            <span>Edit</span>
                          </button>
                        )}
                      </div>
                    </h2>
                    
                    {editingReply ? (
                      <textarea
                        className="w-full p-4 border rounded-lg h-48"
                        value={replyContent}
                        onChange={(e) => setReplyContent(e.target.value)}
                      />
                    ) : (
                      <div className="bg-white border p-4 rounded-lg whitespace-pre-wrap">
                        {replyContent}
                      </div>
                    )}
                    
                    <div className="mt-4 flex justify-end">
                      <button 
                        className={`px-4 py-2 rounded-lg text-white flex items-center space-x-2 ${
                          selectedEmail.status === 'sent' ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'
                        }`}
                        disabled={selectedEmail.status === 'sent' || editingReply}
                        onClick={handleSendReply}
                      >
                        <Send size={16} />
                        <span>{selectedEmail.status === 'sent' ? 'Sent' : 'Send Reply'}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Mail size={48} />
                <p className="mt-2">Select an email to view details</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmailManagementDashboard;
