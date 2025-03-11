// src/api/v1/emails.js
const express = require('express');
const router = express.Router();
const emailsController = require('../../controllers/emailsController');

// Get all emails (filtered)
router.get('/', emailsController.getEmails);

// Get a single email by ID
router.get('/:id', emailsController.getEmailById);

// Update email status
router.patch('/:id/status', emailsController.updateEmailStatus);

// Send a reply using a draft
router.post('/:id/send', emailsController.sendReply);

module.exports = router;

// src/api/v1/drafts.js
const express = require('express');
const router = express.Router();
const draftsController = require('../../controllers/draftsController');

// Get draft by ID
router.get('/:id', draftsController.getDraftById);

// Update draft content
router.put('/:id', draftsController.updateDraft);

// Generate new draft for an email
router.post('/generate', draftsController.generateDraft);

module.exports = router;

// src/api/v1/providers.js
const express = require('express');
const router = express.Router();
const providersController = require('../../controllers/providersController');

// Get all email providers
router.get('/email', providersController.getEmailProviders);

// Get all LLM providers
router.get('/llm', providersController.getLLMProviders);

// Add email provider
router.post('/email', providersController.addEmailProvider);

// Add LLM provider
router.post('/llm', providersController.addLLMProvider);

// Update provider settings
router.put('/:id', providersController.updateProvider);

module.exports = router;
