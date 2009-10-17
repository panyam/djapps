
import datetime, settings,sys
import google
from google import appengine
from google.appengine.ext import db
from djapps.dynamo.gaehelpers import get_or_create_object, get_object_id

def get_foreignsite_by_url(url):
    # return HostSite(site_url = url)
    return None

def get_or_create_useralias(user_id, host_site):
    aliases = UserAlias.all();
    aliases.filter("user_id = ", user_id)
    aliases.filter("host_site = ", host_site)
    if aliases.count() > 0:
        return aliases.fetch(1)[0]
    else:
        alias = UserAlias(user_id = user_id, host_site = host_site)
        alias.put()
        return alias

class LocalSiteProfile(db.Model):
    """
    Default Profile maintained for a user on the local site.
    """
    NOT_REGISTERED          = 0
    AWAITING_CONFIRMATION   = 1
    REGISTERED              = 2

    # 
    # First name of the user
    #
    first_name          = db.StringProperty(default = "")

    # 
    # last name of the user
    #
    last_name           = db.StringProperty(default = "")

    # 
    # nick name of the user
    #
    nick_name           = db.StringProperty(default = "")

    # 
    # user email address
    #
    email               = db.EmailProperty(default = "")

    # 
    # Account type
    #
    # 0 = Free
    #
    # everythign else we will decide later
    #
    accounttype         = db.IntegerProperty(default = 0)

    # 
    # User's web/blog uri
    #
    uri             = db.LinkProperty(default = "")

    # 
    # General profile text/sayings
    #
    text            = db.StringProperty(default = "No Comment")

    # 
    # URL to an image
    #
    image           = db.LinkProperty(default = "")

    # 
    # Registration status
    # 0 - Not Registered
    # 1 - Waiting for confirmation of registration
    # 2 - Registered
    #
    reg_status      = db.IntegerProperty(default = REGISTERED)

# 
# The site which is authenticating the user.
#
# The idea is we want to use any social networking site or 
# container site as a distribution channel for our apps, why 
# create yet another social network???
#
class HostSite(db.Model):
    # 
    # The external site name
    #
    site_name   = db.StringProperty()

    # 
    # URL for the site
    #
    site_url    = db.LinkProperty()

    # 
    # Login url of the site
    #
    site_login_url  = db.LinkProperty()

    def __str__(self):
        return self.site_name + "/" + str(self.site_url)

    # 
    # Returns a json representation
    #
    def toJson(self):
        return {'id': get_object_id(self),
                'site_name': self.site_name,
                'site_url': self.site_url}

# 
# The per-site login of a user.  For each request, this object provides
# authentication attributes for that site.  We can have authentication
# items for more than one site.  
#
# The idea is that we separate the authentication from the actual user
# management.  We will maintain a user profile object that is 
#
# Still to decide:
# 1. Who has controls over which sites are allowed and how are the site
# specific authentication mechanisms/data deciphered by the application?
#
# TODO:
# The primary key tuple is host_site/login_name
#
class UserAlias(db.Model):
    # 
    # The host site/channel from which the user is logging in.
    #
    host_site    = db.ReferenceProperty(HostSite)

    # 
    # The unique id of the user within the host this can be an email or a
    # numeric id or anything really.
    #
    user_id         = db.StringProperty()

    # 
    # Last login time from the foreign site.
    #
    last_login      = db.DateTimeProperty(verbose_name = "last login", auto_now_add = True)

    def __str__(self):
        return self.user_id + "@" + self.host_site.site_name

    # 
    # Returns a json representation
    #
    def toJson(self):
        return {'id': get_object_id(self),
                'host_site': get_object_id(self.host_site) if self.host_site else None,
                'last_login': self.last_login.strftime("%H:%M %d %h %y")}

# 
# A class that maintains the status of similirities between two user
# profiles.
#
# This works as follows:
#
# User Afb logs in from FaceBook
# user Ams logs in from MySpace
#
#
# Ams "selects" Afb and clicks on "that is also me"
#
# Since Afb and Ams have logged in from two different networks, a message
# is sent to Afb requesting confirmation - so Afb can accept this
# "linkage" from FB or from the local site (ie via fb connect).
#
# Once Afb accepts the linkage, Ams's profile is deleted and will now point
# to Afb.
#
# What if:
#
# 1. Bfb also connects and says he is same as Afb - 
#   we can 
#   a: disallow this claiming that both are from the same network.
#   b: allow it and treat Afb and Bfb as the same user - since they point
#      to the same user anyway but not care how they are used - it does not
#      add any technical overhead anyway as only one user profile will be
#      read.
#
# 2. Bfb logs in and says he is same as Ams.  We could do a parent check
# and deduce that Afb is hence Bfb and follow the same strategy as in (1).
# For now we will allow these.
#
class AliasLinkage(db.Model):
    # 
    # The user initiating the similiarity linkage
    #
    alias1  =   db.ReferenceProperty(UserAlias, collection_name = "initiator")

    # 
    # The user accepting the similiarity linkage
    #
    alias2  =   db.ReferenceProperty(UserAlias, collection_name = "acceptor")

    # 
    # Yay or Nay
    #
    response    = db.BooleanProperty()
