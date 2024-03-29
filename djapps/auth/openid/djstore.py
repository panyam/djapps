
"""
A django implementation of the OpenIDStore interface that uses the model
backend as its backing store.
Stores associations, nonces, and authentication tokens.

OpenIDStore is an interface from JanRain's OpenID python library:
  http://openidenabled.com/python-openid/

For more, see openid/store/interface.py in that library.
"""

import datetime

from openid.association import Association as OpenIDAssociation
from openid.store.interface import OpenIDStore
from openid.store import nonce
from models import Association, UsedNonce

# number of associations and nonces to clean up in a single request.
CLEANUP_BATCH_SIZE = 50

class DatastoreStore(OpenIDStore):
    """
    An OpenIDStore implementation that uses django model backend. See
    openid/store/interface.py for in-depth descriptions of the methods.

    They follow the OpenID python library's style, not Google's style, since
    they override methods defined in the OpenIDStore class.
    """

    def storeAssociation(self, server_url, association):
        """
        This method puts a C{L{Association <openid.association.Association>}}
        object into storage, retrievable by server URL and handle.
        """
        assoc = Association(url=server_url,
                            handle=association.handle,
                            association=association.serialize())
        assoc.save()

    def getAssociation(self, server_url, handle=None):
        """
        This method returns an C{L{Association <openid.association.Association>}}
        object from storage that matches the server URL and, if specified, handle.
        It returns C{None} if no such association is found or if the matching
        association is expired.

        If no handle is specified, the store may return any association which
        matches the server URL. If multiple associations are valid, the
        recommended return value for this method is the one that will remain valid
        for the longest duration.
        """
        query = Association.objects.filter(url = server_url)
        if handle:
          query.filter(handle = handle)

        results = query[0]
        if results:
          association = OpenIDAssociation.deserialize(results[0].association)
          if association.getExpiresIn() > 0:
            # hasn't expired yet
            return association
        return None

    def removeAssociation(self, server_url, handle):
        """
        This method removes the matching association if it's found, and returns
        whether the association was removed or not.
        """

        query = Association.gql('WHERE url = :1 AND handle = :2',
                                server_url, handle)
        return self._delete_first(query)

    def useNonce(self, server_url, timestamp, salt):
        """Called when using a nonce.

        This method should return C{True} if the nonce has not been
        used before, and store it for a while to make sure nobody
        tries to use the same value again.  If the nonce has already
        been used or the timestamp is not current, return C{False}.

        You may use L{openid.store.nonce.SKEW} for your timestamp window.

        @change: In earlier versions, round-trip nonces were used and
           a nonce was only valid if it had been previously stored
           with C{storeNonce}.  Version 2.0 uses one-way nonces,
           requiring a different implementation here that does not
           depend on a C{storeNonce} call.  (C{storeNonce} is no
           longer part of the interface.)

        @param server_url: The URL of the server from which the nonce
            originated.

        @type server_url: C{str}

        @param timestamp: The time that the nonce was created (to the
            nearest second), in seconds since January 1 1970 UTC.
        @type timestamp: C{int}

        @param salt: A random string that makes two nonces from the
            same server issued during the same second unique.
        @type salt: str

        @return: Whether or not the nonce was valid.

        @rtype: C{bool}
        """
        query = UsedNonce.gql(
          'WHERE server_url = :1 AND salt = :2 AND timestamp >= :3',
          server_url, salt, self._expiration_datetime())
        return query.fetch(1) == []

    def cleanupNonces(self):
        """Remove expired nonces from the store.

        Discards any nonce from storage that is old enough that its
        timestamp would not pass L{useNonce}.

        This method is not called in the normal operation of the
        library.  It provides a way for store admins to keep
        their storage from filling up with expired data.

        @return: the number of nonces expired.
        @returntype: int
        """
        query = UsedNonce.gql('WHERE timestamp < :1', self._expiration_datetime())
        return self._cleanup_batch(query)

    def cleanupAssociations(self):
        """Remove expired associations from the store.

        This method is not called in the normal operation of the
        library.  It provides a way for store admins to keep
        their storage from filling up with expired data.

        @return: the number of associations expired.
        @returntype: int
        """
        query = Association.gql('WHERE created < :1', self._expiration_datetime())
        return self._cleanup_batch(query)

    def cleanup(self):
        """Shortcut for C{L{cleanupNonces}()}, C{L{cleanupAssociations}()}.

        This method is not called in the normal operation of the
        library.  It provides a way for store admins to keep
        their storage from filling up with expired data.
        """
        return self.cleanupNonces(), self.cleanupAssociations()

    def _delete_first(self, query):
        """Deletes the first result for the given query.

        Returns True if an entity was deleted, false if no entity could be deleted
        or if the query returned no results.
        """
        results = query.fetch(1)

        if results:
          try:
            results[0].delete()
            return True
          except db.Error:
            return False
        else:
          return False

    def _cleanup_batch(self, query):
        """
        Deletes the first batch of entities that match the given query.

        Returns the number of entities that were deleted.
        """
        to_delete = list(query.fetch(CLEANUP_BATCH_SIZE))

        # can't use batch delete since they're all root entities :/
        for entity in to_delete:
          entity.delete()

        return len(to_delete)

    def _expiration_datetime(self):
        """
        Returns the current expiration date for nonces and associations.
        """
        return datetime.datetime.now() - datetime.timedelta(seconds=nonce.SKEW)
