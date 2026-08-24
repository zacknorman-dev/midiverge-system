from __future__ import absolute_import, print_function, unicode_literals
from .Live_Track_Controller import Live_Track_Controller


def create_instance(c_instance):
    return Live_Track_Controller(c_instance)
