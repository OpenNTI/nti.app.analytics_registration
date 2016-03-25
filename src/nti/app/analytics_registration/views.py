#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

import csv
from io import BytesIO

from nti.app.analytics_registration import MessageFactory as _

from zope import interface

from zope.container.contained import Contained

from zope.traversing.interfaces import IPathAdapter

from pyramid.view import view_config

from pyramid import httpexceptions as hexc

from nti.app.base.abstract_views import AbstractAuthenticatedView
from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.app.analytics.utils import set_research_status

from nti.analytics_registration.registration import get_registrations
from nti.analytics_registration.registration import store_registration_data
from nti.analytics_registration.registration import store_registration_survey_data

from nti.common.string import TRUE_VALUES
from nti.common.maps import CaseInsensitiveDict

from nti.dataserver import authorization as nauth

from nti.dataserver.interfaces import IUser

from nti.dataserver.users import User

from nti.externalization.interfaces import StandardExternalFields

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import SUBMIT_REGISTRATION_INFO
from nti.app.analytics_registration import REGISTRATION_READ_VIEW

CLASS = StandardExternalFields.CLASS
LAST_MODIFIED = StandardExternalFields.LAST_MODIFIED

def _is_true(t):
	result = bool(t and str(t).lower() in TRUE_VALUES)
	return result

@interface.implementer(IPathAdapter)
class RegistrationPathAdapter(Contained):

	__name__ = REGISTRATION

	def __init__(self, context, request):
		self.context = context
		self.request = request
		self.__parent__ = context

@view_config(route_name='objects.generic.traversal',
			 name=SUBMIT_REGISTRATION_INFO,
			 context=IUser,
			 renderer='rest',
			 request_method='POST',
			 permission=nauth.ACT_UPDATE)
class RegistrationPostView(AbstractAuthenticatedView,
						   ModeledContentUploadRequestUtilsMixin):
	"""
	We expect regular form POST data here, containing both
	survey and registration information.
	"""
	def _get_research(self, values):
		allow_research = values.get('allow_research')
		return _is_true(allow_research)

	def __get_registration_id_from_store(self, values):
		return 	values.get( 'registration_id', None ) \
			or 	values.get( 'RegistrationId', None )

	def _get_registration_id(self, values):
		# First check the body
		result = self.__get_registration_id_from_store( values )
		if result is None:
			# Then the params
			params = CaseInsensitiveDict( self.request.params )
			result = self.__get_registration_id_from_store( params )
		return result

	def __call__(self):
		values = CaseInsensitiveDict(self.readInput())
		allow_research = self._get_research( values )
		registration_id = self._get_registration_id( values )
		user = self.remoteUser

		set_research_status( user, allow_research )

		# FIXME: Implement
		data = survey_data = None
		store_registration_data( user, registration_id, data )
		if allow_research:
			store_registration_survey_data( user, registration_id, survey_data )
		# FIXME: notify registration event
		return hexc.HTTPNoContent()

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
		# FIXME: Validate these columns
		header_row = [u'username', u'school', u'grade', u'session_date', u'curriculum']
		csv_writer.writerow( header_row )

		for registration in registrations:
			line_data = (registration.user.username,
						 registration.school,
						 registration.grade_teaching,
						 registration.session_date,
						 registration.curriculum)
			csv_writer.writerow( line_data )

		response = self.request.response
		response.body = stream.getvalue()
		response.content_type = str('text/csv; charset=UTF-8')
		response.content_disposition = b'attachment; filename="registrations.csv"'
		return response

