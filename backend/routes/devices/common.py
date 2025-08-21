# centralize common device-related functions

from flask import Blueprint, request, jsonify
from sqlalchemy import text
from config import db
from datetime import datetime, timezone, timedelta
import random, string, requests
from sqlalchemy.exc import IntegrityError


# Global Variables definition
# List of user IDs to exclude from search results NOC service 1123
exclude_users_list = [1, 1123]