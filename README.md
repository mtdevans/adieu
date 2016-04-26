# adieu

adieu is a time-based user enumerator.

## Python Tool Helptext
```
       (                 
    )  )\ ) (    (   (   
 ( /( (()/( )\  ))\ ))\  
 )(_)) ((_)|(_)/((_)((_) 
((_)_  _| | (_|_))(_))(  
/ _` / _` | | / -_) || | 
\__,_\__,_| |_\___|\_,_|                                 

adieu is a time-based user enumerator.

python ./adieu.py ...

Options:
-----------------------------------
        -h,--help               This text.
        -t,--target=    Target, e.g. timebased.ninja:443.
        -p,--parameter= The parameter to cycle through, e.g. username.
        -i,--request=   File containing request, e.g. from Burp.
        -u,--users=             File with one username per line, or colon-separated usernames.
        -r,--reps=              (Optional) Number of repetitions/iterations to perform. Generally, more is better, but watch out for account lockouts.
        -k,--keep-alive (Optional) Set Connection: Keep-Alive on outgoing requests (can improve reliability, speed, and accuracy).
        -n,--preload=   (Optional) To reduce systematic error, preload this many connections and store them in a round-robin-type queue.
        -l,--lockout=   (Optional) For login forms: Max number of attempts per user to avoid account lockouts. --lockout=0 sets to infinity, but still tracks requests (default=3).
        --no-lockout    (Optional) For forgotten password forms: Do not track requests.
        -o,--csv=               (Optional) Output the results as a CSV for importing into Excel etc.
        -P,--ping=              (Optional) Specify the average ping delay (ms) between you and the target. The default is to HEAD favicon.ico 10 times. Disable this with --ping=0.
        -v,--verbose    (Optional) Show verbose logging.
        --with-graph    (Optional) Show a matplotlib graph of results, if available.
        --delay=                (Optional) Sleep ms between requests.
        --requests              (Debugging) Print requests.
        --responses             (Debugging) Print responses.
```

There are quite a few ways unreliable errors creep in when doing time-based tests, especially remotely over the Internet.

This is especially true when the time difference could be less than 10ms which is pretty difficult to detect.

The tool overcomes these errors a few ways:  
1. `--keep-alive` requests that the server keep the connection open so we can send a load of requests down the same open pipe. This is desirable because, especially with TLS-enabled hosts, the TCP and TLS handshakes can be pretty time-consuming.  
2. `--preload=#` creates a round-robin-style array of preloaded connections which removes any delays due to handshakes etc.  
3. `--reps=#` allows you to repeat the results and weedle out errors. Watch out for account lockouts.

Also, the tool attempts to discover the transit time to and from the host using either user-supplied `ping` (e.g. `--ping=30` for 30ms) or `HEAD /favicon.ico HTTP/1.0` 10 times over if no `--ping=` flag is set. You can disable this by setting `--ping=0`.

~~Any obviously-useless results due to network latency issues are discarded and repeated until the result is reasonable.~~ Update: after some real-world testing, this feature has been temporarily pulled back until it can be made more intelligent and tunable.

`--delay=10` adds a 10ms delay between requests if you're concerned about overloading the server.
