################################################################################
# libdv
################################################################################
LIBDV_VERSION = 1.0.0
LIBDV_SITE = http://downloads.sourceforge.net/project/libdv/libdv/$(LIBDV_VERSION)
LIBDV_SOURCE = libdv-$(LIBDV_VERSION).tar.gz
LIBDV_LICENSE = LGPL-2.1+
LIBDV_LICENSE_FILES = COPYING.LIB
LIBDV_INSTALL_STAGING = YES
# No x86 asm on aarch64; skip GTK/SDL example players.
LIBDV_CONF_OPTS = --disable-asm --without-gtk --disable-sdl --disable-gprof
$(eval $(autotools-package))
