#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import csv

from collections import namedtuple

from io import BytesIO

from zope import interface

from zope.container.contained import Contained

from zope.traversing.interfaces import IPathAdapter

from pyramid.view import view_config

from pyramid import httpexceptions as hexc

from nti.app.analytics_registration import MessageFactory as _

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import REGISTRATION_READ_VIEW
from nti.app.analytics_registration import REGISTRATION_UPDATE_VIEW
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES
from nti.app.analytics_registration import REGISTRATION_SURVEY_READ_VIEW
from nti.app.analytics_registration import REGISTRATION_AVAILABLE_SESSIONS

from nti.analytics_registration.registration import get_user_registrations
from nti.analytics_registration.registration import store_registration_rules
from nti.analytics_registration.registration import delete_user_registrations
from nti.analytics_registration.registration import store_registration_sessions

from nti.app.analytics_registration.view_mixins import RegistrationCSVMixin
from nti.app.analytics_registration.view_mixins import RegistrationIDViewMixin
from nti.app.analytics_registration.view_mixins import RegistrationSurveyCSVMixin

from nti.app.base.abstract_views import get_source
from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.common.maps import CaseInsensitiveDict

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseEnrollmentManager

from nti.dataserver import authorization as nauth

from nti.dataserver.users import User

from nti.externalization.interfaces import StandardExternalFields

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.property.property import Lazy

CLASS = StandardExternalFields.CLASS
LAST_MODIFIED = StandardExternalFields.LAST_MODIFIED

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
class RegistrationCSVView( AbstractAuthenticatedView,
						   RegistrationCSVMixin,
						   RegistrationIDViewMixin):
	"""
	An admin view to fetch all registration data.
	"""

	def _get_header_row(self):
		return self._get_registration_header_row()

	def _get_row_data(self, registration):
		return self._get_registration_row_data( registration )

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
class RegistrationSurveyCSVView( RegistrationCSVView,
								 RegistrationSurveyCSVMixin ):
	"""
	An admin view to fetch all registration data and survey data in
	a CSV.
	"""

	def _get_header_row(self):
		result = []
		result.extend( self._get_registration_header_row() )
		result.extend( self._get_registration_survey_header_row() )
		return result

	def _get_row_data(self, registration):
		result = {}
		registration_data = self._get_registration_row_data( registration )
		if not registration_data:
			return None
		result.update( registration_data )
		survey_data = self._get_registration_survey_row_data( registration )
		result.update( survey_data )
		return result

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='POST',
			 name=REGISTRATION_UPDATE_VIEW)
class RegistrationUpdateView(AbstractAuthenticatedView,
							 RegistrationIDViewMixin,
							 ModeledContentUploadRequestUtilsMixin):
	"""
	An admin view to update registration data, via CSV input.
	"""

	@Lazy
	def _update_keys(self):
		keys = [u'employee_id', u'phone', u'school',
				u'grade', u'session_range', u'curriculum']
		return keys

	def _get_input(self):
		source = get_source(self.request, 'csv', 'input', 'source')
		if source is None:
			raise hexc.HTTPUnprocessibleEntity()
		return source

	def __call__(self):
		registration_id = self._get_registration_id()

		csv_input = self._get_input()
		reader = csv.DictReader( csv_input )
		for row in reader:
			username = row.get( 'username' )
			user = User.get_user( username ) if username else None
			if username and user is None:
				logger.warn( 'Skipping user not found %s', username )
				continue
			registrations = get_user_registrations( user,
													registration_id )
			if not registrations:
				return hexc.HTTPNotFound( _('There are no registrations found for %s' % username) )

			for registration in registrations:
				for key in self._update_keys:
					if key in row:
						val = row.get( key )
						if key == 'grade':
							key = 'grade_teaching'
						setattr( registration, key, val )
				logger.info( 'Updated registration data (user=%s) (data=%s)', username, row )
		return hexc.HTTPNoContent()

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
