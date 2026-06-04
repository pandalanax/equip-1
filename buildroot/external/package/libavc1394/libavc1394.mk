################################################################################
# libavc1394
################################################################################
LIBAVC1394_VERSION = 0.5.4
LIBAVC1394_SITE = http://downloads.sourceforge.net/project/libavc1394/libavc1394/$(LIBAVC1394_VERSION)
LIBAVC1394_SOURCE = libavc1394-$(LIBAVC1394_VERSION).tar.gz
LIBAVC1394_LICENSE = LGPL-2.1+
LIBAVC1394_LICENSE_FILES = COPYING
LIBAVC1394_INSTALL_STAGING = YES
LIBAVC1394_DEPENDENCIES = libraw1394 host-pkgconf
$(eval $(autotools-package))
