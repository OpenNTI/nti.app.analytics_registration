#!/usr/bin/env python
# -*- coding: utf-8 -*
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import zope.i18nmessageid
MessageFactory = zope.i18nmessageid.MessageFactory(__name__)

#: The registration path part.
REGISTRATION = 'registration'

#: A POST view to store available sessions for courses.
REGISTRATION_AVAILABLE_SESSIONS = 'RegistrationAvailableSessions'

#: A POST view to submit registration/survey.
SUBMIT_REGISTRATION_INFO = 'SubmitRegistration'

#: A view to return enrollment rules for registration data.
REGISTRATION_ENROLL_RULES = 'RegistrationEnrollRules'

#: The admin view to fetch registration csv.
REGISTRATION_READ_VIEW = 'Registrations'

#: The admin view to update registration information.
REGISTRATION_UPDATE_VIEW = 'UpdateRegistrations'

#: The admin view to fetch registration and survey csv.
REGISTRATION_SURVEY_READ_VIEW = 'RegistrationSurveys'
