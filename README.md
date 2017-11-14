# adieu

adieu is a time-based user discovery tool.

It can discover users on web apps with time delays down to <10 millisecond resolution, if the conditions are right.

adieu consists of two parts: the __data-collector__ (Python script) and a __macro-enabled Excel spreadsheet__ for visualizing the data. On Linux, matplotlib graphs provide this functionality.
## Python Tool Helptext
```
       (                 
    )  )\ ) (    (   (   
 ( /( (()/( )\  ))\ ))\  
 )(_)) ((_)|(_)/((_)((_) 
((_)_  _| | (_|_))(_))(  
/ _` / _` | | / -_) || | 
\__,_\__,_| |_\___|\_,_| 

 adieu discovers app users
   based on time delays

	$ python ./adieu.py ...

Required parameters: (bold indicates short option)
	--target=		Target, e.g. https://timebased.ninja:8443/login.php.
	--users=		File with one username per line, or colon-separated usernames.
	--postdata=		Post data. Specify parameter using a well-placed '???' and adieu will build the request ..OR..
	-i,--request=	File containing raw HTTP request. Replace the parameter with '???'.

Optional parameters:
	--help      	This text.
	--cookiedata=	Cookie data to include in requests.
	--reps=   		Number of repetitions/iterations to perform. Generally, more is better, but watch out for account lockouts.
	--keep-alive	Set Connection: Keep-Alive on outgoing requests (can improve reliability, speed, and accuracy).
	-n,--preload=	To reduce systematic error, preload this many connections and store them in a round-robin-type queue.
	--lockout=		Max attempts per user to avoid locking accounts. -l 0 sets to infinity, but still keeps track of requests (default=3).
	--ignore-lockout	[!Risky!] Use if you aren't concerned about locking accounts out.
	-o,--csv=		Output the results as a CSV for importing into Excel.
	-P,--ping=		Specify the average ping delay (ms) between you and the target. The default is to HEAD favicon.ico 10 times. Disable this with --ping=0.
	--verbose		Show verbose logging.
	--with-graph	Show an Excel or matplotlib graph of results, if available.
	--delay=		Sleep ms between requests.
	--no-encoding	Don't URL encode payloads.
	--outlier-threshold=	Tolerance for accepting a result. The default is 5. It is enabled only if --ignore-lockout and --reps >= 4. To disable, set to zero.
	--requests		(Debugging) Print requests.
	--responses		(Debugging) Print responses.

Example usage:
	Test whether app is vulnerable:
		python ./adieu.py --target=https://test.server/adieuTest.php -u "jeremy:matt" --postdata="user=???&pass=badPass" --ignore-lockout --reps=3 --csv=out1.csv

	Discover other users using request file:
		python ./adieu.py -i adieuRequest.txt --parameter=username --target=https://test.server -u "barry:admin:jeremy:matt:jim" --ignore-lockout --with-graph --csv=out2.csv
```

## Graph Plotter
Running with `--with-graph` will open up Excel automatically on Windows. Alternatively, you can import the CSV at a later point (e.g. if running on Linux) by opening the .xslm file.

The macro supports Excel 2016, and not Excel 2010.
### Graph types
There are two graphs produced depending on the number of users tested.

If only two are supplied, the tool assumes the format is testing the difference in delay between valid and invalid accounts.
This is generally the first step in discovering if the website is vulnerable.

If more than two are supplied, the tool creates a graph with the usernames along the x-axis and a trace of the mean time delays across repetitions.
You'll generally need three repetitions for a reliable result, though if you can see the effect from just one request per account the issue can be considered more serious (>info).
### Editing graphs
Because the graphs source their data from Excel, you can delete any dodgy-looking results and the graphs will auto-update.
### Avoiding Account Lockouts
If you're testing a login form, there's a chance you'll lock accounts out because of a bunch of failed login attempts.

To avoid this, the tool keeps track of attempts per user per site, along with the lockout limit per site. Set `--lockout=n` for a maximum of `n` attempts per account.

The database is stored in `adieu_lockout_protection.csv` in whatever folder you're in.

If there is no account lockout or you're testing a forgotten password form and aren't bothered, set `--ignore-lockout`.

Any obviously useless results due to network latency issues are discarded and repeated until the result is reasonable.
This is still somewhat experimental and not yet perfect.
The default is to take the middle 30% and rerun results which fall greater than five standard deviations from the mean of this.
The value is tweakable with `--outlier-threshold`. Setting it to zero disables this feature.
Note: it only activates when `--ignore-lockout` is enabled and at least four repetitions are used (it's difficult to take percentiles of three results..!)
