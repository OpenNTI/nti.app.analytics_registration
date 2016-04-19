#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

from hamcrest import is_
from hamcrest import none
from hamcrest import is_not
from hamcrest import has_item
from hamcrest import has_items
from hamcrest import has_entry
from hamcrest import has_length
from hamcrest import has_entries
from hamcrest import assert_that
from hamcrest import has_property
from hamcrest import has_properties
does_not = is_not

import os
import csv

from six import StringIO

from zope import component
from zope.intid import IIntIds

from nti.analytics.stats.interfaces import IAnalyticsStatsSource

from nti.app.testing.decorators import WithSharedApplicationMockDS
from nti.app.testing.application_webtest import ApplicationLayerTest

from nti.contenttypes.courses.interfaces import ICourseInstance
from nti.contenttypes.courses.interfaces import ICourseCatalogEntry

from nti.contenttypes.courses.utils import get_enrollment_catalog
from nti.contenttypes.courses.index import IX_USERNAME

import nti.dataserver.tests.mock_dataserver as mock_dataserver

from nti.dataserver.users import User

from nti.ntiids.ntiids import find_object_with_ntiid

from nti.analytics_registration.registration import get_user_registrations

from nti.app.products.courseware.tests import InstructedCourseApplicationTestLayer

from nti.app.analytics_registration import REGISTRATION
from nti.app.analytics_registration import REGISTRATION_READ_VIEW
from nti.app.analytics_registration import SUBMIT_REGISTRATION_INFO
from nti.app.analytics_registration import REGISTRATION_ENROLL_RULES
from nti.app.analytics_registration import REGISTRATION_AVAILABLE_SESSIONS

from nti.analytics_registration.stats import _RegistrationStatsSource

class TestAnalyticsRegistration(ApplicationLayerTest):

	layer = InstructedCourseApplicationTestLayer

	default_origin = b'http://janux.ou.edu'
	course_ntiid = 'tag:nextthought.com,2011-10:NTI-CourseInfo-Fall2015_CS_1323'
	#course_ntiid2 = 'tag:nextthought.com,2011-10:OU-HTML-CLC3403_LawAndJustice.course_info'

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
		assert_that( res.get( 'RegistrationRules',
								has_entry( self.school,
									has_entry( self.grade,
											has_item(
												has_entries( 'course_ntiid', self.course_ntiid,
															 'course', self.curriculum ))))))
		# We map to one course...
		assert_that( res.get( 'CourseSessions' ), has_length( 1 ) )
		assert_that( res.get( 'CourseSessions' ), has_entry( self.course_ntiid,
															 has_length( 36 )))

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

	def _test_enrolled(self, username, enrolled=True):
		"""
		Validate the given username is enrolled in our course.
		"""
		with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
			catalog = get_enrollment_catalog()
			records = tuple( catalog.apply( {IX_USERNAME:{'any_of':(username,)}}))
			if not enrolled:
				assert_that( records, has_length( 0 ))
			else:
				assert_that( records, has_length( 1 ))
				intids = component.getUtility(IIntIds)
				course = intids.queryObject( records[0] ).CourseInstance
				entry = ICourseCatalogEntry( course )
				assert_that( entry.ntiid, is_( self.course_ntiid ))

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
		new_username = 'Phil_Krundle'
		submit_url2 = '/dataserver2/users/%s/%s' % (new_username, SUBMIT_REGISTRATION_INFO)

		# Upload registration rules.
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=True )

		# We can re-upload and still be valid
		self._upload_rules( reg_params, get_rules_url, sessions=False, rules=True )
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=False )
		self._upload_rules( reg_params, get_rules_url, sessions=True, rules=True )

		list_response = [1,2,3,4,5]
		text_response = 'Jax'
		session = 'July 25-26 (M/T)'
		phone = ''
		employee_id = 'Employee Eleventeen'
		form_data = { 'school': self.school,
					  'grade': 6,
					  'course': self.course_ntiid,
					  'session': session,
					  'employee_id': employee_id,
					  'survey_text' : text_response,
					  'survey_list' : list_response }
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

		self._test_enrolled( 'sjohnson@nextthought.com' )

		def _get_registrations_csv( reg_id=self.registration_id ):
			csv_params = {'registration_id':reg_id}
			res = self.testapp.get( self.registrations_url, params=csv_params )
			return tuple( csv.DictReader( StringIO( res.body ) ) )

		# Get registrations again
		csv_output = _get_registrations_csv()
		assert_that( csv_output, has_length( 1 ))
		registered = csv_output[0]
		assert_that( registered.get( 'username' ), is_( 'sjohnson@nextthought.com' ) )
		assert_that( registered.get( 'grade' ), is_( self.grade ) )
		assert_that( registered.get( 'curriculum' ), is_( self.curriculum ) )
		assert_that( registered.get( 'school' ), is_( self.school ) )
		assert_that( registered.get( 'phone' ), is_( phone ) )
		assert_that( registered.get( 'session_range' ), is_( session ) )
		assert_that( registered.get( 'employee_id' ), is_( employee_id ))

		# Already registered.
		self.testapp.post_json( submit_url, form_data, status=422 )

		# Test db state
		with mock_dataserver.mock_db_trans(self.ds):
			# Empty
			new_user1 = self._create_user( username=new_username )
			user_registrations = get_user_registrations( new_user1, self.registration_id )
			assert_that( user_registrations, has_length( 0 ))

			# User's survey responses
			user = User.get_user( 'sjohnson@nextthought.com' )
			user_registrations = get_user_registrations( user, self.registration_id )
			assert_that( user_registrations, has_length( 1 ))
			user_registration = user_registrations[0]
			assert_that( user_registration.survey_submission, has_length( 1 ))
			survey = user_registration.survey_submission[0]
			assert_that( survey.details, has_length( 2 ))
			assert_that( survey.details, has_items(
											has_properties( 'question_id', 'survey_list',
															'response', list_response ),
											has_properties( 'question_id', 'survey_text',
															'response', text_response ) ))

		# Two users, two different sessions; form_data2 has new session, reg_id, version.
		registration_id2 = 'Registration2'
		session2 = 'Session Range2'
		form_data2 = dict( form_data )
		form_data2['registration_id'] = registration_id2
		form_data2['session'] = session2
		form_data2['version'] = 'Survey.v1'
		new_user_env = self._make_extra_environ( new_username )

		# With no rules for reg_id, the supplied cousre_ntiid does not validate.
		self.testapp.post_json( submit_url, form_data2, status=422 )

		self._upload_rules( {'registration_id': registration_id2},
							get_rules_url, sessions=True, rules=True )
		self.testapp.post_json( submit_url, form_data2 )
		self._test_enrolled( new_username, enrolled=False )
		self.testapp.post_json( submit_url2, form_data, extra_environ=new_user_env )
		self._test_enrolled( new_username )
		self.testapp.post_json( submit_url2, form_data2, extra_environ=new_user_env )

		csv_output = _get_registrations_csv()
		assert_that( csv_output, has_length( 2 ))
		assert_that( csv_output, has_items(
									has_entries( 'username', 'sjohnson@nextthought.com',
												 'session_range', session ),
									has_entries( 'username', new_username,
												 'session_range', session )))

		csv_output = _get_registrations_csv( registration_id2 )
		assert_that( csv_output, has_length( 2 ))
		assert_that( csv_output, has_items(
									has_entries( 'username', 'sjohnson@nextthought.com',
												 'session_range', session2 ),
									has_entries( 'username', new_username,
												 'session_range', session2 )))

		# Test stats
		with mock_dataserver.mock_db_trans(self.ds, site_name='platform.ou.edu'):
			course = find_object_with_ntiid( self.course_ntiid )
			course = ICourseInstance( course )
			subs = component.subscribers( (user, course), IAnalyticsStatsSource )
			subs = [x for x in subs if isinstance(x, _RegistrationStatsSource)]
			assert_that( subs, has_length( 1 ))
			stats = subs[0]
			# We have multiple records mapping to the same course
			# assert_that( stats.RegistrationSurveyStats.survey_version, none())
			# assert_that( stats.RegistrationStats.session_range, is_(session))
			assert_that( stats.RegistrationSurveyStats, has_property( 'survey_text', text_response ))
			assert_that( stats.RegistrationSurveyStats, has_property( 'survey_list', list_response ))
			assert_that( stats.RegistrationStats.school, is_(self.school))
			assert_that( stats.RegistrationStats.grade_teaching, is_(self.grade))
			assert_that( stats.RegistrationStats.curriculum, is_(self.curriculum))
			assert_that( stats.RegistrationStats.employee_id, is_(employee_id))
			assert_that( stats.RegistrationStats.phone, none())

		# Test admin view removing registrations
		delete_url = '/dataserver2/registration/RemoveRegistrations'

		# No params
		self.testapp.post_json( delete_url, {}, status=422 )

		self.testapp.post_json( delete_url, {'user':'sjohnson@nextthought.com'} )
		self._test_enrolled( 'sjohnson@nextthought.com', enrolled=False )
		self._test_enrolled( new_username )

		# Validate one user remains
		csv_output = _get_registrations_csv()
		assert_that( csv_output, has_length( 1 ))
		assert_that( csv_output, has_item(
									has_entries( 'username', new_username,
												 'session_range', session )))

		csv_output = _get_registrations_csv( registration_id2 )
		assert_that( csv_output, has_length( 1 ))
		assert_that( csv_output, has_item(
									has_entries( 'username', new_username,
												 'session_range', session2 )))

		# Now delete by registration id
		self.testapp.post_json( delete_url, {'registration_id': self.registration_id} )

		self.testapp.get( self.registrations_url, params=reg_params, status=404 )

		csv_output = _get_registrations_csv( registration_id2 )
		assert_that( csv_output, has_length( 1 ))
		assert_that( csv_output, has_item(
									has_entries( 'username', new_username,
												 'session_range', session2 )))

