#!/bin/bash

# add all changes
git add .

# commit (with default message if none provided)
commit_message=${1:-"auto commit"}
git commit -m "$commit_message"

# push to remote
git push
