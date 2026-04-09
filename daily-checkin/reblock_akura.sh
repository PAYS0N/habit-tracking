#!/bin/bash
# Reblock akura_malice after a video game session expires.
# Invoked by a transient systemd timer scheduled via schedule_akura_reblock().
/usr/sbin/ipset del allowed_internet 192.168.22.52
