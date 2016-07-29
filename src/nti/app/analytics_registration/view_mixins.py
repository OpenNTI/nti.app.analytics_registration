#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import nameparser

from zope import component

from nti.analytics_registration.registration import get_all_survey_questions

from nti.app.analytics_registration import MessageFactory as _

from pyramid import httpexceptions as hexc

from nti.common.maps import CaseInsensitiveDict

from nti.common.property import Lazy

from nti.dataserver.interfaces import IUsernameSubstitutionPolicy

from nti.dataserver.users import User

from nti.dataserver.users.interfaces import IUserProfile

def replace_username(username):
	substituter = component.queryUtility(IUsernameSubstitutionPolicy)
	if substituter is None:
		return username
	result = substituter.replace(username) or username
	return result

class RegistrationIDViewMixin(object):
	"""
	A mixin to get the required registration id.
	"""

	def __get_registration_id_from_store(self, values):
		if not values:
			return None
		return 	values.get( 'registration_id', None ) \
			or 	values.get( 'RegistrationId', None )

	def _get_registration_id(self, values=None, strict=True):
		"""
		Get the required registration id associated with this request.
		If `strict`, will raise a 422 if not given.
		"""
		# First check the body
		result = self.__get_registration_id_from_store( values )
		if result is None:
			# Then the params
			params = CaseInsensitiveDict( self.request.params )
			result = self.__get_registration_id_from_store( params )
		if result is None and strict:
			raise hexc.HTTPUnprocessableEntity( _('No registration id given.') )
		return result

	def _get_names_and_email(self, user, username):
		profile = IUserProfile( user )
		external_id = replace_username(username)

		realname = profile.realname or ''
		if realname and '@' not in realname and realname != username:
			human_name = nameparser.HumanName(realname)
			firstname = human_name.first or ''
			lastname = human_name.last or ''
		else:
			firstname = ''
			lastname = ''
		email = getattr( profile, 'email', '' )
		return external_id, firstname, lastname, email

	def _get_registration_row_data(self, registration):
		if not registration.user:
			logger.warn( 'User no longer exists' )
			return
		username = registration.user.username
		user = User.get_user( username )
		if user is None:
			logger.warn( 'User not found (%s)', username )
			return
		username, first, last, email = self._get_names_and_email( user, username )
		if email and email.endswith( '@nextthought.com' ):
			return
		line_data = {'username': username,
					 'first_name': first,
					 'last_name': last,
					 'registration_date': registration.timestamp,
					 'employee_id': registration.employee_id,
					 'email': email,
					 'phone': registration.phone,
					 'school': registration.school,
					 'grade': registration.grade_teaching,
					 'session_range': registration.session_range,
					 'curriculum': registration.curriculum}
		return line_data

class RegistrationCSVMixin( object ):

	def _get_registration_header_row(self):
		header_row = [u'username', u'first_name', u'last_name',
					  u'registration_date', u'employee_id', u'email',
					  u'phone', u'school', u'grade', u'session_range',
					  u'curriculum']
		return header_row

class RegistrationSurveyCSVMixin(RegistrationCSVMixin):

	def _get_question_key(self, question_id):
		# Remove whitespace
		return '_'.join( question_id.split() )

	def _get_survey_display(self, question_id):
		return 'Survey: %s' % question_id

	@Lazy
	def _survey_question_map(self):
		"""
		Map survey question identifier to display version.
		"""
		registration_id = self._get_registration_id()
		survey_questions = get_all_survey_questions( registration_id )
		survey_question_map = {self._get_question_key( x ): self._get_survey_display( x )
							   for x in survey_questions}
		return survey_question_map

	def _get_registration_survey_header_row(self):
		header_row = []
		header_row.append( 'survey_version' )
		questions = sorted( self._survey_question_map.values() )
		header_row.extend( questions )
		return header_row

	def _get_registration_survey_row_data(self, registration):
		line_data = {}
		survey_submission = registration.survey_submission[0]
		line_data['survey_version'] = survey_submission.survey_version

		# Gather our user responses
		user_results = {}
		for submission in survey_submission.details:
			key = self._get_question_key( submission.question_id )
			response = submission.response
			if isinstance( response, list ):
				# Make sure our list response is readable.
				response = ', '.join( (str(x) for x in response) )
			user_results[ key ] = response

		# Now map to our result set, making sure to provide empty string
		# for no-responses.
		for key, display in self._survey_question_map.items():
			line_data[display] = user_results.get( key, '' )
		return line_data
