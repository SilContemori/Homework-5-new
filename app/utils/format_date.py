from datetime import datetime

def format_date(d):
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.strftime('%Y-%m-%d')
    return str(d)