#!/bin/bash

### UI & Appearance ###
# Switch to dark mode
osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to 1'
# Hide recent apps from Dock
defaults write com.apple.dock show-recents -bool false
# Set Dock auto-hide delay to disabled
defaults write com.apple.Dock autohide-delay -float 0


### Finder Preferences ###
# Always open everything in Finder's column view
defaults write com.apple.Finder FXPreferredViewStyle clmv
# Finder: show hidden files by default
defaults write com.apple.finder AppleShowAllFiles -bool true
# Finder: show all filename extensions
defaults write NSGlobalDomain AppleShowAllExtensions -bool true
# Finder: home directory as default
defaults write com.apple.finder NewWindowTarget -string "PfHm"
defaults write com.apple.finder NewWindowTargetPath -string "file://${HOME}"
# Finder: allow text selection in Quick Look
defaults write com.apple.finder QLEnableTextSelection -bool true
# Finder: don't create .ds files on mounted storages
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true
# Hide external drives or removable media from the desktop
defaults write com.apple.finder ShowExternalHardDrivesOnDesktop -bool false
defaults write com.apple.finder ShowRemovableMediaOnDesktop -bool false



### Input & Keyboard ###
# Disable press-and-hold for keys in favor of key repeat
defaults write -g ApplePressAndHoldEnabled -bool false
# Set keyboard repeat rate
defaults write NSGlobalDomain KeyRepeat -int 1
defaults write NSGlobalDomain InitialKeyRepeat -int 15
# Turn off keyboard illumination when computer is not used for 60 sec
defaults write com.apple.BezelServices kDimTime -int 60
# Automatically illuminate built-in MacBook keyboard in low light
defaults write com.apple.BezelServices kDim -bool true
# Disable smart quotes as they're annoying when typing code
# defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
# Disable smart dashes as they're annoying when typing code
# defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false
# Disable automatic emoji substitution (i.e., use plain text smileys)
# defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "automaticEmojiSubstitutionEnablediMessage" -bool false
# Disable smart quotes as it's annoying for messages that contain code
# defaults write com.apple.messageshelper.MessageController SOInputLineSettings -dict-add "automaticQuoteSubstitutionEnabled" -bool false



### Security & Privacy ###
# Require password immediately after sleep or screen saver begins
defaults write com.apple.screensaver askForPassword -int 1
defaults write com.apple.screensaver askForPasswordDelay -int 0



### Sound ###
# Disable audio feedback when volume is changed
defaults write com.apple.sound.beep.feedback -bool false



### Network ###
# Use AirDrop over every interface
defaults write com.apple.NetworkBrowser BrowseAllInterfaces 1




### System Utilities ###
# Reset Launchpad
find ~/Library/Application\ Support/Dock -name "*.db" -maxdepth 1 -delete
