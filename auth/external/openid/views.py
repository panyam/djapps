
import datetime, random, sha, sys, logging, urlparse
from django.conf import settings
from django.template import RequestContext, loader
from django.http import HttpResponseRedirect, HttpResponse

import  djapps.utils.decorators     as djdecos
import  djapps.utils.request        as djrequest
import  djapps.utils.json           as djjson
from    djapps.utils                import api_result
from    djapps.utils                import urls as djurls
from    djapps.auth                 import REDIRECT_FIELD_NAME

from openid import fetchers
from openid.consumer.consumer import Consumer
from openid.consumer import discover
from openid.extensions import pape, sreg

if settings.USING_APPENGINE:
    import gaefetcher as fetcher
    import gaestore as store
else:
    # TODO: Implement the fetcher and store for django
    import djfetcher as fetcher
    import djstore as store

consumer_instance = False
def get_consumer(request):
    assert hasattr(request, 'session'), "The openid module requires session middleware to be installed. Edit your MIDDLEWARE_CLASSES setting to insert 'gaeutils.middle.middleware.SessionMiddleware' in GAE or 'django.contrib.sessions.middleware.SessionMiddleware' in django."

    consumer_instance = None
    if not consumer_instance:
        fetchers.setDefaultFetcher(fetcher.UrlfetchFetcher())
        consumer_instance = Consumer(request.ms_session, store.DatastoreStore())

    return consumer_instance

# 
# The initiate url is called when the user selects to "sign in with XXX"
# At this point we redirect the OpenID Provider's authentication page.
# When it is done, the OP will redirect to the url specified in the
# redirect_field_name that will be part of the POST request.
#
# Now why are we doing this instead of having a special
# openid_login_complete url?  This is because the openid provider will
# callback with a whole bunch of openid.XXX variables which our middleware
# can intercept anyway.  So why duplicate that work here again?
#
# Also the same openid.XXX parameters that come in will also have an
# authentication status.  ie success and failure and other things.
#
def openid_login_initiate(request, redirect_field_name = REDIRECT_FIELD_NAME):
    if request.method == "GET":
        # redirect back to the login page
        return HttpResponseRedirect(djurls.get_login_url())
    elif request.method == "POST":
        # paramount!  without this no XRDS can be fetched 
        openid_url = request.POST.get('openid_url')
        if not openid_url:
            return api_result(-1, "OpenID Provider URL Not Specified")

        the_consumer = get_consumer(request)
        if not the_consumer:
            return api_result(-1, "Could not create consumer")

        try:
            auth_request = the_consumer.begin(openid_url)
        except discover.DiscoveryFailure, e:
            logging.error("Error during OpenID provider discovery: " + str(e))
            return api_result(-1, e)
        except discover.XRDSError, e:
            logging.error("Error parsing XRDS from provider: " + str(e))
            return api_result(-1, e)

        request.session.claimed_id = auth_request.endpoint.claimed_id
        request.session.server_url = auth_request.endpoint.server_url
        request.session.save()

        sreg_request = sreg.SRegRequest(optional=['nickname', 'fullname', 'email'])
        auth_request.addExtension(sreg_request)
        pape_request = pape.Request([pape.AUTH_MULTI_FACTOR,
                                     pape.AUTH_MULTI_FACTOR_PHYSICAL,
                                     pape.AUTH_PHISHING_RESISTANT,
                                     ])
        auth_request.addExtension(pape_request)

        redirect_to = request.REQUEST.get(redirect_field_name, '')
        full_url    = djurls.get_site_url() + "/" + request.get_full_path()

        parts       = list(urlparse.urlparse(full_url))
        parts[2]    = redirect_to
        parts[4]    = 'session_id=%s' % request.ms_session.sid
        parts[5]    = ''
        return_to   = urlparse.urlunparse(parts)
        realm       = urlparse.urlunparse(parts[0:2] + [''] * 4)

        redirect_url = auth_request.redirectURL(realm, return_to)
        logging.debug('Redirecting to %s' % redirect_url)
        return HttpResponseRedirect(redirect_url)

