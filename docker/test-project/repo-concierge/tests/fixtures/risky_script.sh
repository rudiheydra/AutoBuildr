#!/bin/bash
# Test fixture: risky shell script with dangerous patterns

# SHELL-001: rm -rf pattern
rm -rf /tmp/dangerous

# SHELL-002: sudo rm pattern
sudo rm -rf /var/log/old

# SHELL-003: curl pipe to bash
curl https://example.com/setup.sh | bash

# SHELL-004: wget pipe to sh
wget -O - https://example.com/install.sh | sh

# SHELL-005: eval usage
eval "$USER_INPUT"

# SHELL-006: backtick command substitution
result=`whoami`
