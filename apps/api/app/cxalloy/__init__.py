"""CxAlloy integration.

The API on the current plan is **read only** (docs/adr/0001). Nothing in this
package writes to CxAlloy, and the client interface has no write method for
anyone to reach for by accident. Results leave as an export package a person
imports.
"""
