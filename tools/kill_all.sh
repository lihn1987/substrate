#!/bin/bash
ps -ef | grep substrate | grep -v grep |awk '{print $2}' | xargs kill -9
