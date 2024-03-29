import datetime, random, sys, logging

from django.conf import settings
from django.template import RequestContext, loader
from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect, HttpResponse
from django.views.decorators.cache import never_cache
from djapps.dynamo.helpers import get_or_create_object, get_first_object, save_object, get_object_id
from djapps.utils import urls as djurls
from djapps.utils import codes
from djapps.auth import REDIRECT_FIELD_NAME

from models import *
import api

import  djapps.utils.decorators     as djdecos
import  djapps.utils.request        as djrequest
import  djapps.utils.json           as djjson
from    djapps.utils                import api_result

#
# Processes POST request on the registration form
#
# This wont be called directly but by an application specific view!
#
# Returns (on a GET method):
#   the http rendered on a given template, with a structure with the key
#   context assigned to form_context
#
# Returns (on a POST method):
#   Output form with 3 variables:
#       'form':     The current form - not really necessary
#       'context':  The form context specified by the caller
#       'error':    If there were any errors in the creation
#
# Otherwise:
#   'InvalidMethod': True
#
# TODO:
# give a "prefix" parameter that would prefix all fields by a certain
# string to avoid conflicts.
#
@djdecos.format_response
def account_register(request,
             template_name      = 'djapps/auth/register.html',
             email_template     = "djapps/auth/register-email.txt",
             email_from         = "accounts@thisserver.com",
             email_subject      = "Your Account Confirmation",
             register_timeout   = 2,
             form_context       = {}):

    format = djrequest.get_var(request, settings.FORMAT_PARAM, "").strip().lower()

    if request.method == 'GET':
        return api_result(codes.CODE_OK, {'context': form_context}), template_name
    elif request.method != 'POST' or request.GET.get("__method__", "") == "post":
        return api_result(codes.CODE_NOTALLOWEDMETHOD, "Invalid request method"), template_name

    #
    # Create the form the submitted data
    #
    post_data       = request.POST
    UserClass       = api.LocalUser
    if 'UserClass' in form_context:
        UserClass   = form_context['UserClass']

    UserRegClass    = LocalUserRegistration
    if 'UserRegClass' in form_context:
        UserRegClass = form_context['UserRegClass']

    username = djrequest.get_var(request, "username", "").strip().lower()
    email = djrequest.get_var(request, "email", "").strip().lower()
    password = djrequest.get_var(request, "password", "").strip()
    if not email:
        return api_result(codes.CODE_GENERAL_ERROR, "Email is mandatory")

    #
    # Form is now validated
    #
    is_active = True
    first_name = last_name = nick_name = ""
    if 'first_name' in post_data: first_name = post_data['first_name']
    if 'last_name' in post_data: last_name = post_data['last_name']
    if 'nick_name' in post_data: nick_name = post_data['nick_name']
    new_user, reg_info, new_created = api.register_user(email, email, password, first_name, last_name, nick_name,
                                                        is_active, request, register_timeout, form_context,
                                                        UserClass, UserRegClass, email_template,  email_from,
                                                        email_subject)
    # batch save the registration and user objects
    # if reg_info: save_object(new_user, reg_info)
    # else: save_object(new_user)

    if new_created:
        return api_result(codes.CODE_OK, {'id': str(get_object_id(new_user)),
                                  'username': new_user.username}), HttpResponseRedirect(djurls.get_login_url())
    else:
        message = "User already exists.  Please enter a new username."
        return api_result(codes.CODE_USERNAME_TAKEN, message), HttpResponse(message)

def account_login(request,
                  template_name='djapps/auth/login.html',
                  redirect_field_name=REDIRECT_FIELD_NAME,
                  request_context = None):
    """
    Displays the login form and handles the login action.
    """
    from djapps.auth.local import forms as authforms
    redirect_to = request.REQUEST.get(redirect_field_name, '')
    # Light security check -- make sure redirect_to isn't garbage.
    if not redirect_to or ' ' in redirect_to:
        redirect_to = settings.LOGIN_REDIRECT_URL
    if request.method == "POST" or request.GET.get("__method__", "") == "post":
        format = djrequest.get_var(request, settings.FORMAT_PARAM, "").strip().lower()
        username = djrequest.get_var(request, "username", "").strip().lower()
        email = djrequest.get_var(request, "email", "").strip().lower()
        password = djrequest.get_var(request, "password", "").strip()

        login_user = None
        if username and password:
            login_user = api.authenticate(request, username, password)
            if login_user is None:
                return api_result(codes.CODE_AUTH_FAILED, "Authentication failed.")
            elif not login_user.is_active:
                return api_result(codes.CODE_ACCOUNT_INACTIVE, "Account is inactive.")
            else:
                api.login(request, login_user)
                if request.session.test_cookie_worked():
                    request.session.delete_test_cookie()

        if not login_user:
            return api_result(codes.CODE_AUTH_FAILED, "Authentication failed."), HttpResponseRedirect(djurls.get_login_url())
        elif not login_user.is_active:
            return api_result(codes.CODE_ACCOUNT_UNCONFIRMED, "Email confirmation not yet recieved.")
        else:
            # valid user
            return api_result(codes.CODE_OK,
                              {'id': str(get_object_id(login_user)),
                               'username': login_user.username}), HttpResponseRedirect(redirect_to)

    request.session.set_test_cookie()
    return {'form': {}, redirect_field_name: redirect_to, }, template_name

@djdecos.format_response
def decorated_account_login(request, **kwargs):
    """
    Essentially wraps the account_login function with a format_response
    decorator to return a HttpResponse object instead of raw data.
    To get only raw data use the account_login function.
    """
    return account_login(request, **kwargs)

@djdecos.format_response
def normal_account_logout(request):
    if settings.USING_APPENGINE:
        # how to log out?
        assert "GAE Cannot logout yet"
    else:
        from django.contrib.auth.views import logout
        logout(request)

    next_page = djrequest.get_getvar(request, "next", "/")
    return HttpResponseRedirect(next_page or request.path)

#
# Confirm the registration - called when the user, clicks on the link in
# the confirmation email
#
# Returns a response with:
#   if successful:
#       'confirmed':    True
#   if failure:
#       'expired':      Registration window expired
#
@djdecos.format_response
def account_confirm(request,
            activation_key,
            confirm_template = 'djapps/auth/confirm.html',
            form_context = {}):
    UserClass       = LocalUser
    if 'UserClass' in form_context:
        UserClass   = form_context['UserClass']

    UserRegClass    = LocalUserRegistration
    if 'UserRegClass' in form_context:
        UserRegClass = form_context['UserRegClass']

    reg_info    = get_first_object(UserRegClass, activation_key = activation_key)

    if reg_info:
        if reg_info.key_expires < datetime.datetime.today():
            return render_to_response(confirm_template, {'expired': True, 'context': form_context})

        reg_info.user.is_active  = True
        reg_info.user.save()
    else:
        return HttpResponseRedirect(djurls.get_login_url())

    return HttpResponseRedirect('/?present_login=true')

#
# GET requests return the settings page.
# POST requests allow you to update particular settings.  Not all settings
# have to be updated at the same time.
#
# Returns:
#   In JSON mode - api_result(code, result) as usual
#   Otherwise template renderered (possibly with an errors object upon
#   error in POST).
#
@djdecos.format_response
def account_settings(request,
                     template_name = "djapps/auth/settings.html",
                     extra_context = {}):
    format = None
    if settings.FORMAT_PARAM in request.GET:
        format = request.GET[settings.FORMAT_PARAM]

    if request.method == 'GET':
        return extra_context, template_name
    elif request.method != 'POST':
        message = "Invalid request type: " + request.method
        return api_result(codes.CODE_NOTALLOWEDMETHOD, message), HttpResponse(message)

