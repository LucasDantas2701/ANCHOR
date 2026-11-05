"""
The local interface: a server on this computer only, and the Angular app it serves.

The server reads and acts through the same functions as the command line (the automation store,
the runner); it adds no rules of its own. Every API request must carry the code made at each
start, and come from the app's own address: no other program or website can drive ANCHOR.
"""
