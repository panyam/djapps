
from django.utils.translation import ugettext_lazy as _
from django.db import models
import api as idgenapi

class StringIDField(models.Field):
    """
    A field that can be used to provide random IDs.
    """
    description = _("A field that can create random IDs using an id generator.")
    def __init__(self, idgen, key_length, *args, **kwargs):
        assert idgen != None, "%ss must have a valid idgen field value" % self.__class__.__name__
        assert key_length and key_length > 0, "%ss must have a positive key_length" % self.__class__.__name__
        self.id_genfunc = idgen
        self.id_generator = None
        self.key_length = key_length
        self.initialised = False
        super(StringIDField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        """
        Get the DB Type.
        """
        return 'varchar(%d)' % self.key_length

    def pre_save(self, model_instance, add):
        """
        Returns field's value just before saving.
        """
        print "Model Instance, id, Add, Value: ", model_instance, model_instance.id, add, getattr(model_instance, self.attname)
        if add: # new instance so create a new ID value
            # if the idgen is a string then we can use it as is
            if type(self.id_genfunc) in (str, unicode):
                value = idgenapi.get_next_id(self.id_genfunc)
            else:
                # otherwise it is a function so call it and call the next
                # id on the returned the idgen as we could have runtime
                # idgens
                value = idgenapi.get_next_id(self.id_genfunc(model_instance))
            setattr(model_instance, self.attname, value)
            return value 
        else:
            super(StringIDField, self).pre_save(model_instance, add)

    def get_internal_type(self):
        return "CharField"

    def to_python(self, value):
        if isinstance(value, basestring) or value is None:
            return value
        return smart_unicode(value)

    def get_prep_value(self, value):
        return self.to_python(value)

