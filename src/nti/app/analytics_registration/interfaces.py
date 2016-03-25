#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

from zope import interface

from nti.dataserver.interfaces import IUser

from nti.schema.field import Dict
from nti.schema.field import Object

class IUserRegistrationSurveySubmissionEvent(interface.Interface):
	"""
	An event signaling a user has submitted a registration survey.
	"""

	user = Object(IUser, title="The user")
	registration_data = Dict(title="The registration data submitted by the user.")

@interface.implementer(IUserRegistrationSurveySubmissionEvent)
class UserRegistrationSurveySubmissionEvent( object ):

	def __init__(self, user, data):
		self.user = user
		self.registration_data = data
