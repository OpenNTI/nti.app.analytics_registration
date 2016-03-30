#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_
from hamcrest import none
from hamcrest import is_in
from hamcrest import is_not
from hamcrest import has_key
from hamcrest import contains
from hamcrest import not_none
from hamcrest import has_item
from hamcrest import has_items
from hamcrest import has_entry
from hamcrest import has_length
from hamcrest import assert_that
from hamcrest import greater_than
from hamcrest import has_property
does_not = is_not

from nti.schema.testing import validly_provides

import fudge

import os
from itertools import chain

import simplejson

from nti.contenttypes.courses.interfaces import ICourseInstance

from nti.contenttypes.presentation.utils import prepare_json_text

from nti.externalization.externalization import to_external_object

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.app.testing.decorators import WithSharedApplicationMockDS
from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.dataserver.tests import mock_dataserver

from nti.app.products.courseware.tests import InstructedCourseApplicationTestLayer

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import REGISTRATION_READ_VIEW
from nti.app.analytics_registration import SUBMIT_REGISTRATION_INFO
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES
from nti.app.analytics_registration import REGISTRATION_AVAILABLE_SESSIONS

class TestAnalyticsRegistration(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	default_origin = b'http://janux.ou.edu'
	course_ntiid = 'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2015_CS_1323'

	sessions_url = '/dataserver2/%s/%s' % ( REGISTRATION, REGISTRATION_AVAILABLE_SESSIONS )
	rules_url = '/dataserver2/%s/%s' % ( REGISTRATION, REGISTRATION_ENROLL_RULES )
	registrations_url = '/dataserver2/%s/%s' % ( REGISTRATION, REGISTRATION_READ_VIEW )

	registration_id = 'ClockmakersLie'

	school = 'Federick, Lilla G. Middle'
	grade = '6'
	curriculum  = 'Building a Lunar Colony'

	def _get_csv_data(self, filename):
		path = os.path.join(os.path.dirname(__file__), filename)
		with open( path, 'r' ) as f:
			result = f.read()
		return result

	@WithSharedApplicationMockDS(testapp=True, users=True)
	def test_registration(self):
		# Admin views
		# Empty registrations
		reg_params = {'registration_id' : self.registration_id }
		self.testapp.get( self.registrations_url,
						  params=reg_params,
						  status=404 )

		# Upload registration rules.
		rules_csv = self._get_csv_data( 'course_rules.csv' )
		sessions_csv = self._get_csv_data( 'course_sessions.csv' )
		self.testapp.post( self.sessions_url,
							upload_files=[('sessions', 'foo.csv', sessions_csv)],
						   	params=reg_params)
		self.testapp.post( self.rules_url,
							upload_files=[('rules', 'foo.csv', rules_csv)],
							params=reg_params)

		# Fetch rules
		get_rules_url = '/dataserver2/users/sjohnson@nextthought.com/%s' % REGISTRATION_ENROLL_RULES
		submit_url = '/dataserver2/users/sjohnson@nextthought.com/%s' % SUBMIT_REGISTRATION_INFO
		res = self.testapp.get( get_rules_url, params=reg_params )
		res = res.json_body
		assert_that( res.get( 'MimeType' ), is_('application/vnd.nextthought.analytics.registrationrules') )
		assert_that( res.get( 'Class' ), is_('RegistrationRules') )
		assert_that( res.get( 'RegistrationRules' ), has_length( 1 ) )
		assert_that( res.get( 'RegistrationRules', has_entry( self.school,
															  has_entry( self.grade,
																		 is_( self.curriculum )))))
		# Six courses
		assert_that( res.get( 'CourseSessions' ), has_length( 6 ) )
		# Six sessions for course
		assert_that( res.get( 'CourseSessions' ), has_entry( self.curriculum,
															 has_length( 6 )))
