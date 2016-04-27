#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import csv
import nameparser

from nti.app.analytics_registration import MessageFactory as _

from collections import namedtuple

from io import BytesIO

from zope import interface
from zope import component

from zope.container.contained import Contained

from zope.traversing.interfaces import IPathAdapter

from pyramid.view import view_config

from pyramid import httpexceptions as hexc

from nti.app.analytics_registration.view_mixins import RegistrationIDViewMixin

from nti.app.base.abstract_views import get_source
from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.analytics_registration.registration import get_user_registrations
from nti.analytics_registration.registration import get_all_survey_questions
from nti.analytics_registration.registration import store_registration_rules
from nti.analytics_registration.registration import delete_user_registrations
from nti.analytics_registration.registration import store_registration_sessions

from nti.common.maps import CaseInsensitiveDict

from nti.common.property import Lazy

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseEnrollmentManager

from nti.dataserver import authorization as nauth

from nti.dataserver.interfaces import IUsernameSubstitutionPolicy

from nti.dataserver.users import User

from nti.dataserver.users.interfaces import IUserProfile

from nti.externalization.interfaces import StandardExternalFields

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import REGISTRATION_READ_VIEW
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES
from nti.app.analytics_registration import REGISTRATION_SURVEY_READ_VIEW
from nti.app.analytics_registration import REGISTRATION_AVAILABLE_SESSIONS

CLASS = StandardExternalFields.CLASS
LAST_MODIFIED = StandardExternalFields.LAST_MODIFIED

def replace_username(username):
	substituter = component.queryUtility(IUsernameSubstitutionPolicy)
	if substituter is None:
		return username
	result = substituter.replace(username) or username
	return result

@interface.implementer(IPathAdapter)
class RegistrationPathAdapter(Contained):

	__name__ = REGISTRATION

	def __init__(self, context, request):
		self.context = context
		self.request = request
		self.__parent__ = context

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='GET',
			 name=REGISTRATION_READ_VIEW)
class RegistrationCSVView(AbstractAuthenticatedView,
						  RegistrationIDViewMixin):
	"""
	An admin view to fetch all registration data.
	"""

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

	def _get_header_row(self):
		header_row = [u'username', u'first_name', u'last_name',
					  u'employee_id', u'email', u'phone',
					  u'school', u'grade', u'session_range', u'curriculum']
		return header_row

	def _get_row_data(self, registration):
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
					 'employee_id': registration.employee_id,
					 'email': email,
					 'phone': registration.phone,
					 'school': registration.school,
					 'grade': registration.grade_teaching,
					 'session_range': registration.session_range,
					 'curriculum': registration.curriculum}
		return line_data

	def __call__(self):
		values = CaseInsensitiveDict( self.request.params )
		username = values.get( 'user' ) or values.get( 'username' )
		registration_id = self._get_registration_id()

		user = User.get_user( username )
		# Optionally filter by user or registration id.
		registrations = get_user_registrations( user,
												registration_id )
		if not registrations:
			return hexc.HTTPNotFound( _('There are no registrations') )

		stream = BytesIO()
		header_row = self._get_header_row()
		csv_writer = csv.DictWriter( stream, header_row )
		csv_writer.writeheader()

		registrations = sorted( registrations, key=lambda x: x.timestamp )
		for registration in registrations:
			line_data = self._get_row_data( registration )
			if line_data:
				csv_writer.writerow( line_data )

		response = self.request.response
		response.body = stream.getvalue()
		response.content_type = str('text/csv; charset=UTF-8')
		response.content_disposition = b'attachment; filename="registrations.csv"'
		return response

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='GET',
			 name=REGISTRATION_SURVEY_READ_VIEW)
class RegistrationSurveyCSVView( RegistrationCSVView ):
	"""
	An admin view to fetch all registration data and survey data in
	a CSV.
	"""

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
							   for x in survey_questions }
		return survey_question_map

	def _get_row_data(self, registration):
		line_data = super( RegistrationSurveyCSVView, self )._get_row_data( registration )
		survey_submission = registration.survey_submission[0]
		line_data['survey_version'] = survey_submission.survey_version

		# Gather our user responses
		user_results = {}
		for submission in survey_submission.details:
			key = self._get_question_key( submission.question_id )
			user_results[ key ] = submission.response

		# Now map to our result set, making sure to provide empty string
		# for no-responses.
		for key, display in self._survey_question_map.items():
			line_data[display] = user_results.get( key, '' )
		return line_data

	def _get_header_row(self):
		header_row = super( RegistrationSurveyCSVView, self )._get_header_row()
		header_row.append( 'survey_version' )
		questions = sorted( self._survey_question_map.values() )
		header_row.extend( questions )
		return header_row

RegistrationEnrollmentRule = namedtuple( 'RegistrationEnrollmentRule',
										 ('school',
										  'curriculum',
										  'grade',
										  'course_ntiid'))

RegistrationSessions = namedtuple( 'RegistrationSessions',
									('curriculum',
									 'session_range',
									 'course_ntiid'))

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='POST',
			 name=REGISTRATION_AVAILABLE_SESSIONS)
class RegistrationSessionsPostView(AbstractAuthenticatedView,
								   ModeledContentUploadRequestUtilsMixin,
								   RegistrationIDViewMixin):
	"""
	An admin view to push registration sessions to server. We expect
	these columns in the inbound csv:

		* course/curriculum
		* session_range
		* course_ntiid
	"""

	def __call__(self):
		values = CaseInsensitiveDict(self.readInput())
		registration_id = self._get_registration_id( values )
		source = get_source(self.request, 'sessions', 'csv', 'input')
		if source is None:
			raise hexc.HTTPUnprocessableEntity( _('No CSV file found.') )

		session_infos = []
		csv_input = csv.reader( source )
		# Skip header
		next( csv_input, None )
		for row in csv_input:
			if not row or row[0].startswith("#") or not ''.join( row ).strip():
				continue
			if not (row[0] and row[1] and row[2]):
				raise hexc.HTTPUnprocessableEntity( 'Line with missing data (%s)' % row )
			session_info = RegistrationSessions( row[0], row[1], row[2] )
			session_infos.append( session_info )

		if not session_infos:
			raise hexc.HTTPUnprocessableEntity( _('No session information given.') )

		store_count = store_registration_sessions( registration_id, session_infos )
		logger.info( 'Registration session rules stored (count=%s)', store_count )
		return hexc.HTTPCreated()

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='POST',
			 name=REGISTRATION_ENROLL_RULES)
class RegistrationEnrollmentRulesPostView(AbstractAuthenticatedView,
										  ModeledContentUploadRequestUtilsMixin,
										  RegistrationIDViewMixin):
	"""
	An admin view to push registration rules to server. We expect
	these columns in the inbound csv:

		* school
		* course/curriculum
		* grade
		* course_ntiid
	"""

	def __call__(self):
		values = CaseInsensitiveDict(self.readInput())
		registration_id = self._get_registration_id( values )
		source = get_source(self.request, 'rules', 'csv', 'input')
		if source is None:
			raise hexc.HTTPUnprocessableEntity( _('No CSV input given.') )

		rules = []
		csv_input = csv.reader( source )
		# Skip header
		next( csv_input, None )
		for row in csv_input:
			if not row or row[0].startswith("#") or not ''.join( row ).strip():
				continue
			if not (row[0] and row[1] and row[2] and row[3]):
				raise hexc.HTTPUnprocessableEntity( 'Line with missing data (%s)' % row )
			enroll_rule = RegistrationEnrollmentRule( row[0],
													  row[1],
													  row[2],
													  row[3] )
			rules.append( enroll_rule )

		if not rules:
			raise hexc.HTTPUnprocessableEntity( _('No rules given.') )

		store_count = store_registration_rules( registration_id, rules )
		logger.info( 'Registration enrollment rules stored (count=%s)',
					 store_count )
		return hexc.HTTPCreated()

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='POST',
			 name='RemoveRegistrations')
class RemoveRegistrationsView(AbstractAuthenticatedView,
							  ModeledContentUploadRequestUtilsMixin,
							  RegistrationIDViewMixin):
	"""
	Delete the registrations by user and registration id. This should
	only be used by admins in test environments. By default, users
	are unenrolled from corresponding course.
	"""

	def __call__(self):
		params = CaseInsensitiveDict(self.readInput())
		username = params.get( 'user' ) or params.get( 'username' )
		registration_id = self._get_registration_id( params, strict=False )
		unenroll = params.get( 'unenroll', True )
		user = None
		if username:
			user = User.get_user( username )

		# For safety, make sure they are sure.
		if user is None and not registration_id and not params.get( 'force' ):
			raise hexc.HTTPUnprocessableEntity(
							_('No username or registration id, must force.') )

		deleted = delete_user_registrations( user, registration_id )
		logger.info( 'Deleted %s user registrations (user=%s) (registration=%s)',
					len( deleted ), username, registration_id )

		# Now unenroll our users.
		if unenroll:
			for registration, course_ntiid in deleted:
				course = find_object_with_ntiid( course_ntiid )
				course = ICourseInstance( course, None )
				if course is not None:
					manager = ICourseEnrollmentManager( course )
					manager.drop( registration.user )
					logger.info( 'User unenrolled (%s) (%s)',
								 registration.user, course_ntiid )
				else:
					logger.warn( 'No course found for (%s) (%s)',
								 registration.user, course_ntiid )
		return hexc.HTTPNoContent()
