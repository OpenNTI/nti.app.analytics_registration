#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.app.analytics_registration import MessageFactory as _

from collections import namedtuple

from datetime import datetime

from pyramid.view import view_config

from pyramid import httpexceptions as hexc

from nti.app.analytics_registration.view_mixins import RegistrationIDViewMixin

from nti.app.base.abstract_views import AbstractAuthenticatedView

from nti.app.externalization.view_mixins import ModeledContentUploadRequestUtilsMixin

from nti.analytics_registration.exceptions import NoUserRegistrationException
from nti.analytics_registration.exceptions import DuplicateUserRegistrationException
from nti.analytics_registration.exceptions import DuplicateRegistrationSurveyException

from nti.analytics_registration.registration import get_registration_rules
from nti.analytics_registration.registration import store_registration_data
from nti.analytics_registration.registration import get_registration_sessions
from nti.analytics_registration.registration import store_registration_survey_data
from nti.analytics_registration.registration import get_course_ntiid_for_user_registration

from nti.common.maps import CaseInsensitiveDict

from nti.contenttypes.courses.interfaces import ES_CREDIT_NONDEGREE

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry
from nti.contenttypes.courses.interfaces import ICourseEnrollmentManager

from nti.dataserver import authorization as nauth

from nti.dataserver.interfaces import IUser

from nti.externalization.interfaces import LocatedExternalDict
from nti.externalization.interfaces import StandardExternalFields

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.analytics_registration import SUBMIT_REGISTRATION_INFO
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES

CLASS = StandardExternalFields.CLASS
MIMETYPE = StandardExternalFields.MIMETYPE

RegistrationData = namedtuple( 'RegistrationData',
								('school',
								 'grade_teaching',
								 'curriculum',
								 'phone',
								 'session_range'))

@view_config(route_name='objects.generic.traversal',
			 name=SUBMIT_REGISTRATION_INFO,
			 context=IUser,
			 renderer='rest',
			 request_method='POST',
			 permission=nauth.ACT_UPDATE)
class SubmitRegistrationView(AbstractAuthenticatedView,
						     ModeledContentUploadRequestUtilsMixin,
						     RegistrationIDViewMixin):
	"""
	We expect regular form POST data here, containing both
	survey and registration information.
	"""

	def _get_registration_data(self, values):
		"""
		From the given values dict, return a tuple of registration data
		and the remainder key/value dict of survey responses.
		"""
		for non_survey_key in ( 'registration_id', 'RegistrationId' ):
			values.pop( non_survey_key, None )
		# Optional
		phone = values.pop( 'phone', None )
		try:
			school = values.pop( 'school' )
			grade_teaching = values.pop( 'grade' )
			curriculum = values.pop( 'course' )
			session_range = values.pop( 'session' )
		except KeyError:
			raise hexc.HTTPUnprocessableEntity( _('Missing registration value.') )
		registration_data = RegistrationData( school,
											  grade_teaching,
											  curriculum,
											  phone,
											  session_range )
		return registration_data, values

	def _enroll(self, user, registration_id):
		"""
		Enroll the user in the course mapping to their registration.
		"""
		course_ntiid = get_course_ntiid_for_user_registration( user, registration_id )
		course = None
		if course_ntiid:
			course = find_object_with_ntiid( course_ntiid )
			course = ICourseInstance( course, None )

		if course is None:
			raise hexc.HTTPUnprocessableEntity( _('Course not found during registration.') )

		manager = ICourseEnrollmentManager(course)
		# XXX: We do not have an comparable scope for this type
		# of enrollment, CREDIT_NONDEGREE is an approximation.
		record = manager.enroll( user, scope=ES_CREDIT_NONDEGREE )

		entry = ICourseCatalogEntry( course, None )
		entry_ntiid = entry.ntiid if entry is not None else ''
		logger.info( 'User enrolled in course during registration (%s) (%s)',
					 user, entry_ntiid )
		return record

	def _store_data(self, user, registration_id, values):
		"""
		Store the registration and survey data
		"""
		timestamp = datetime.utcnow()
		data, survey_data = self._get_registration_data( values )
		try:
			store_registration_data( user, timestamp, registration_id, data )
		except DuplicateUserRegistrationException:
			raise hexc.HTTPUnprocessableEntity( _('User already registered for this session.') )

		try:
			store_registration_survey_data( user, timestamp,
											registration_id,
											survey_data )
		except NoUserRegistrationException:
			# Should not be possible.
			raise hexc.HTTPUnprocessableEntity( _('User not yet registered.') )
		except DuplicateRegistrationSurveyException:
			raise hexc.HTTPUnprocessableEntity(
							_('User already submitted survey for this session.') )

	def __call__(self):
		values = CaseInsensitiveDict(self.readInput())
		registration_id = self._get_registration_id( values )
		user = self.remoteUser

		self._store_data( user, registration_id, values )
		record = self._enroll( user, registration_id )
		return record

@view_config(route_name='objects.generic.traversal',
			 renderer='rest',
			 permission=nauth.ACT_READ,
			 context=IUser,
			 request_method='GET',
			 name=REGISTRATION_ENROLL_RULES)
class RegistrationRulesView(AbstractAuthenticatedView,
							RegistrationIDViewMixin):
	"""
	Retrieves the registration possibilities. Results
	should be returned in feed order.
	"""

	def __call__(self):
		registration_id = self._get_registration_id()
		rules = get_registration_rules( registration_id )
		sessions = get_registration_sessions( registration_id )
		if not rules or not sessions:
			raise hexc.HTTPNotFound( _('No registration rules found.') )

		result = LocatedExternalDict()
		result[CLASS] = 'RegistrationRules'
		result[MIMETYPE] = 'application/vnd.nextthought.analytics.registrationrules'

		result['RegistrationRules'] = registration_dict = {}
		result['CourseSessions'] = course_session_dict = {}

		# Set the courses available per school and grade.
		for rule in rules:
			grade_dict = registration_dict.setdefault( rule.school, dict() )
			course_list = grade_dict.setdefault( rule.grade_teaching, list() )
			course_list.append( rule.curriculum )

		# Set the sessions available per course/curriculum.
		for session in sessions:
			session_list = course_session_dict.setdefault( session.curriculum, list() )
			session_list.append( session.session_range )

		return result
