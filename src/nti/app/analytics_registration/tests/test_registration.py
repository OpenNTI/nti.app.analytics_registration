#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_
from hamcrest import is_not
from hamcrest import has_entry
from hamcrest import has_length
from hamcrest import assert_that
does_not = is_not

import os
import csv

from six import StringIO

from nti.app.testing.decorators import WithSharedApplicationMockDS
from nti.app.testing.application_webtest import ApplicationLayerTest

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

	def _test_rules(self, url, reg_params):
		res = self.testapp.get( url, params=reg_params )
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

	def _upload_rules(self, reg_params, get_rules_url, sessions=True, rules=True):
		"""
		Uploads data and validates state.
		"""
		if sessions:
			sessions_csv = self._get_csv_data( 'course_sessions.csv' )
			self.testapp.post( self.sessions_url,
								upload_files=[('sessions', 'foo.csv', sessions_csv)],
							   	params=reg_params)
		if rules:
			rules_csv = self._get_csv_data( 'course_rules.csv' )
			self.testapp.post( self.rules_url,
								upload_files=[('rules', 'foo.csv', rules_csv)],
								params=reg_params)
		# Validate
		self._test_rules( get_rules_url, reg_params )

	@WithSharedApplicationMockDS(testapp=True, users=True)
	def test_registration(self):
		# Admin views
		# Empty registrations
		reg_params = {'registration_id' : self.registration_id }
		self.testapp.get( self.registrations_url,
						  params=reg_params,
						  status=404 )

		get_rules_url = '/dataserver2/users/sjohnson@nextthought.com/%s' % REGISTRATION_ENROLL_RULES
		submit_url = '/dataserver2/users/sjohnson@nextthought.com/%s' % SUBMIT_REGISTRATION_INFO

		# Upload registration rules.
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=True )

		# We can re-upload and still be valid
		self._upload_rules( reg_params, get_rules_url, sessions=False, rules=True )
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=False )
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=True )

		form_data = { 'school': self.school,
					  'grade': 6,
					  'course': self.curriculum,
					  'phone': '867-5309',
					  'session': 'July 25-26 (M/T)',
					  'survey_freetext' : 'bleh',
					  'survey_list' : [1,2,3,4,5] }
		form_data.update( reg_params )

		# Missing field
		bad_data = dict( form_data )
		bad_data.pop( 'course' )
		self.testapp.post_json( submit_url, bad_data, status=422 )

		# No mapping for grade
		bad_grade = dict( form_data )
		bad_grade['grade'] = 7
		self.testapp.post_json( submit_url, bad_grade, status=422 )

		# No mapping for school
		bad_school = dict( form_data )
		bad_school['school'] = 'HardKnocks'
		self.testapp.post_json( submit_url, bad_school, status=422 )

		# Submit with enrollment
		res = self.testapp.post_json( submit_url, form_data )
		res = res.json_body
		assert_that( res.get( 'Class' ), is_('CourseInstanceEnrollment') )
		assert_that( res.get( 'MimeType' ),
					 is_('application/vnd.nextthought.courseware.courseinstanceenrollment') )
		assert_that( res.get( 'CatalogEntryNTIID' ), is_( self.course_ntiid ) )

		# Get registrations again
		res = self.testapp.get( self.registrations_url, params=reg_params )
		csv_output = tuple( csv.DictReader( StringIO( res.body ) ) )
		assert_that( csv_output, has_length( 1 ))
		registered = csv_output[0]
		assert_that( registered.get( 'username' ), is_( 'sjohnson@nextthought.com' ) )
		assert_that( registered.get( 'grade' ), is_( self.grade ) )
		assert_that( registered.get( 'curriculum' ), is_( self.curriculum ) )
		assert_that( registered.get( 'school' ), is_( self.school ) )
		assert_that( registered.get( 'phone' ), is_( '867-5309' ) )
		assert_that( registered.get( 'session_range' ), is_( 'July 25-26 (M/T)' ) )

		# Already registered.
		self.testapp.post_json( submit_url, form_data, status=422 )

