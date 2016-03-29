#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.app.analytics_registration import MessageFactory as _

from zope.event import notify

from pyramid.view import view_config

from pyramid import httpexceptions as hexc

from nti.app.analytics.utils import set_research_status

from nti.app.analytics_registration.interfaces import UserRegistrationSurveySubmissionEvent

from nti.app.analytics_registration.view_mixins import RegistrationIDPostViewMixin

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.analytics_registration.registration import store_registration_data
from nti.analytics_registration.registration import store_registration_survey_data

from nti.common.string import TRUE_VALUES
from nti.common.maps import CaseInsensitiveDict

from nti.dataserver import authorization as nauth

from nti.dataserver.interfaces import IUser

from nti.externalization.interfaces import StandardExternalFields

from nti.app.analytics_registration import SUBMIT_REGISTRATION_INFO

CLASS = StandardExternalFields.CLASS
LAST_MODIFIED = StandardExternalFields.LAST_MODIFIED

def _is_true(t):
	result = bool(t and str(t).lower() in TRUE_VALUES)
	return result

@view_config(route_name='objects.generic.traversal',
			 name=SUBMIT_REGISTRATION_INFO,
			 context=IUser,
			 renderer='rest',
			 request_method='POST',
			 permission=nauth.ACT_UPDATE)
class SubmitRegistrationView(AbstractAuthenticatedView,
						     ModeledContentUploadRequestUtilsMixin,
						     RegistrationIDPostViewMixin):
	"""
	We expect regular form POST data here, containing both
	survey and registration information.
	"""

	def _get_research(self, values):
		allow_research = values.get('allow_research')
		return _is_true(allow_research)

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
		# FIXME: Enroll and return
		notify( UserRegistrationSurveySubmissionEvent( user, data ))
		return hexc.HTTPNoContent()

