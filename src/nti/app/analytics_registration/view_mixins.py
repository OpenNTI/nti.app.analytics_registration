#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. $Id$
"""

from __future__ import print_function, unicode_literals, absolute_import, division
__docformat__ = "restructuredtext en"

logger = __import__('logging').getLogger(__name__)

from nti.app.analytics_registration import MessageFactory as _

from pyramid import httpexceptions as hexc

from nti.common.maps import CaseInsensitiveDict

class RegistrationIDPostViewMixin(object):
	"""
	A mixin to get the required registration id.
	"""

	def __get_registration_id_from_store(self, values):
		return 	values.get( 'registration_id', None ) \
			or 	values.get( 'RegistrationId', None )

	def _get_registration_id(self, values):
		"""
		Get the registration id associated with this POST.
		"""
		# First check the body
		result = self.__get_registration_id_from_store( values )
		if result is None:
			# Then the params
			params = CaseInsensitiveDict( self.request.params )
			result = self.__get_registration_id_from_store( params )
		if result is None:
			raise hexc.HTTPUnprocessableEntity( _('No registration id given.') )
		return result

