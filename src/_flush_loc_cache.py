"""Flush stale location cache (loc:states, loc:districts:*) so the API serves
fresh state codes after the list_states_live() fix."""

import jobs

c = jobs.redis_conn()
keys = [k.decode() if isinstance(k, bytes) else k for k in c.scan_iter("loc:*")]
print("found", len(keys), "loc keys:", keys)
if keys:
    c.delete(*keys)
    print("deleted", len(keys))
print("remaining:", [k.decode() if isinstance(k, bytes) else k for k in c.scan_iter("loc:*")])
