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

from nti.app.analytics_registration.view_mixins import RegistrationIDPostViewMixin

from nti.app.base.abstract_views import get_source
from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.analytics_registration.registration import get_registrations
from nti.analytics_registration.registration import store_registration_rules
from nti.analytics_registration.registration import store_registration_sessions

from nti.common.maps import CaseInsensitiveDict

from nti.dataserver import authorization as nauth

from nti.dataserver.interfaces import IUser
from nti.dataserver.interfaces import IUsernameSubstitutionPolicy

from nti.dataserver.users import User

from nti.dataserver.users.interfaces import IUserProfile

from nti.externalization.interfaces import StandardExternalFields

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import REGISTRATION_READ_VIEW
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES
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
class RegistrationCSVView(AbstractAuthenticatedView):
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

	def __call__(self):
		values = CaseInsensitiveDict( self.readInput() )
		username = values.get( 'user' ) or values.get( 'username' )
		registration_id = values.get( 'registration_id' ) or values.get( 'RegistrationId' )

		user = User.get_user( username )
		# Optionally filter by user or registration id.
		registrations = get_registrations( user=user, registration_id=registration_id )
		if not registrations:
			return hexc.HTTPNotFound( _('There are no registrations') )

		stream = BytesIO()
		csv_writer = csv.writer( stream )
		header_row = [u'username', u'first_name', u'last_name', u'email', u'phone',
					  u'school', u'grade', u'session_range', u'curriculum']
		csv_writer.writerow( header_row )

		for registration in registrations:
			username = registration.user.username
			user = User.get_user( username )
			if user is None:
				logger.warn( 'User not found (%s)', username )
				continue
			username, first, last, email = self._get_names_and_email( user, username )
			line_data = (username,
						 first,
						 last,
						 email,
						 registration.phone,
						 registration.school,
						 registration.grade_teaching,
						 registration.session_range,
						 registration.curriculum)
			csv_writer.writerow( line_data )

		response = self.request.response
		response.body = stream.getvalue()
		response.content_type = str('text/csv; charset=UTF-8')
		response.content_disposition = b'attachment; filename="registrations.csv"'
		return response

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
								   RegistrationIDPostViewMixin):
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
		source = get_source(self.request, 'csv', 'input')
		if source is None:
			raise hexc.HTTPUnprocessableEntity( _('No CSV file found.') )

		session_infos = []
		for row in csv.reader(source):
			if not row or row[0].startswith("#"):
				continue
			session_info = RegistrationSessions( row[0], row[1], row[2] )
			session_infos.append( session_info )

		if not session_infos:
			raise hexc.HTTPUnprocessableEntity( _('No session information given.') )

		store_registration_sessions( registration_id, session_infos )
		return hexc.HTTPCreated()

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_NTI_ADMIN,
			 context=RegistrationPathAdapter,
			 request_method='POST',
			 name=REGISTRATION_ENROLL_RULES)
class RegistrationEnrollmentRulesPostView(AbstractAuthenticatedView,
										  RegistrationIDPostViewMixin):
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
		source = get_source(self.request, 'csv', 'input')
		if source is None:
			raise hexc.HTTPUnprocessableEntity( _('No CSV file found.') )

		rules = []
		for row in csv.reader(source):
			if not row or row[0].startswith("#"):
				continue
			enroll_rule = RegistrationEnrollmentRule( row[0],
													  row[1],
													  row[2],
													  row[3] )
			rules.append( enroll_rule )

		if not rules:
			raise hexc.HTTPUnprocessableEntity( _('No rules given.') )

		store_registration_rules( registration_id, rules )
		return hexc.HTTPCreated()
