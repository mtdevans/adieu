#!/usr/bin/python
import socket
import time
try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse
import urllib
from builtins import range
import datetime
import ssl
import sys, getopt
import numpy
# For opening Excel.
import os
import subprocess
# End Excel.
from colorama import * 
try:
    import matplotlib.pyplot as plt
except:
    print("[!] Install MatPlotLib to visualize the tool's output.\n")

numpy.set_printoptions(precision=3) # Numpy decimal places.
numpy.seterr(all='raise') # Turn warnings into exceptions.

# Define some global variables. (Probably not the most elegant way).
inputfile = ''
outputfile = ''
host = ''
port = 80
use_ssl = False
target = "" # The target host.
ping = None
parameter = "-" # Parameter in the POST request file to cycle through.
reps = 1 # Number of cycles.
preload = 0 # Number of connexions to pre-open.
keepalive = False # Set request Connection header to hold socket open.
showrequests = False # Print requests.
showresponses = False # Print server responses.
verbose = False # Print all logged info.
users = '' # Either valid:invalid or a \n-separated list.
withgraph = False # Plot graph on linux.
delay_between_requests = 0.1 # Sleep between requests.
dont_urlencode = False # Don't urlencode test parameters.
outlier_threshold = 5. # Larger means more permissive. Zero disables.
rejected_outliers_count = 0 # Keep count for stats' sake.

# Colorama requires this.
init()

# Request building stuff.
postdata = "" # Post parameters.
cookiedata = "" # Cookies.
headers = [
            ["Host", "localhost"],
            ["User-Agent", "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.110 Safari/537.36 Vivaldi/1.0.435.42"],
            ["Content-Type", "application/x-www-form-urlencoded; charset=UTF-8"],
            ["Content-Length", "0"],
            ["Connection", "Close"]
          ]

# Account lockout protection.
lockout_filename = 'adieu_lockout_protection.csv'
lockout = []
lockout_disable = False # This flag disables all lockout tracking, logging, and warnings.
lockout_limit = -1
lockout_limit_default = 3 # Set to 3 by default.
lockout_displayed_users = [] # This keeps track of which users have reached lockout.

# Array to hold pre-loaded connexions.
queue = []
preload_counter = 0 # Counter to index in queue.

userlist = [] # To be populated.

x_values = []
y_values = []

results = []

def client():
    global results,keepalive,userlist,x_values,y_values,preload,preload_counter,queue,withgraph,delay_between_requests
    global lockout_limit,lockout_disable,lockout_displayed_users,parameter,target,use_ssl,host,port,postdata,cookiedata,dont_urlencode,outlier_threshold,rejected_outliers_count
    
    baseline_error = 0.0
    
    if inputfile is '' and postdata is '':
        error("No request data specified.")
        exit()
    
    if users is '':
        error("No users specified.")
        exit()
        
    # Load users
    if ":" in users:
        # valid:invalid
        userlist = users.split(':')
    else:
        # Users file.
        with open(users, 'r') as uf:
            userlist = uf.read().split('\n')
        
    # Remove empty entries.
    userlist = list(filter(None, userlist))
        
    if len(userlist) < 2:
        error("Need at least two users.")
        exit()

    ## Parse the target.
    target_parsed = urlparse(target)
    port = target_parsed.port
    host = target_parsed.netloc.split(":")[0]
    requestfile = target_parsed.path
    if target_parsed.scheme == 'https': use_ssl = True
    if port == None:
        if target_parsed.scheme == "http":
            port = 80
            use_ssl = False
        elif target_parsed.scheme == "https":
            port = 443
            use_ssl = True
    
    if port == None and host == '':
        if target_parsed.path != '':
            host = target_parsed.path.split(":")[0]
            port = int(target_parsed.path.split(":")[1])
            if port in [443, 8443]:
                use_ssl = True
            else:
                use_ssl = False
    
    if host is '':
        print("No host specified.")
        exit()
    if port is 0 or port is None:
        print("No port specified.")

    ## Read file or build request.
    if inputfile is not '':
        with open(inputfile, 'r') as f:
            filecontents = f.read()
    else:
        # Build request.
        postdata = postdata.split('&')
        
        # Figure out which parameter to use.
        postdata2 = []
        foundone = 0
        for i in postdata:
            args = i.split('=')
            if args[1] == "?" or args[1] == "???":
                args[1] = "???"
                foundone += 1
            postdata2.append(args[0] + "=" + args[1])
        postdata = '&'.join([str(x) for x in postdata2])
        if foundone is not 1:
            error("Please use one ? in the postdata to denote which parameter we are cycling through.")
            exit()
        
        # Make sure first character is slash.
        if requestfile[0] != "/":
            requestfile = "/" + requestfile
        filecontents = "POST " + requestfile + " HTTP/1.1\n"
        # Add headers.
        for header in headers:
            filecontents += header[0] + ": " + header[1] + "\n"
        # Add cookies.
        if len(cookiedata) > 0:
            filecontents += "Cookie: " + cookiedata + "\n"
        
        filecontents += "\n"
        filecontents += postdata
        
        filecontents = filecontents.replace("Host: localhost", "Host: " + host + ":" + str(port))
        
    filecontents = filecontents.replace("\r\n", "\n").rstrip('\n')
    
    if parameter != '-':
        parameters = filecontents.split('\n\n', 1)[-1].split('&')
        
        for i in parameters:
            args = i.split('=')
            if args[0] == parameter:
                filecontents = filecontents.replace(i, args[0] + "=" + "???")
    
    if not "???" in filecontents:
        if parameter == '-':
            error("Please include ??? in the request file at the desired location, or specify the correct parameter using '-p username'.")
        else:
            error("Unable to locate parameter '" + parameter + "'.")
        if verbose:
            print("\nFull request:\n------------\n")
            print(filecontents + "\n")
        exit()

    
    ## Account lockout system.
    if lockout_disable:
        log("Account lockout disabled.", True)
    else:
        # Lockout protection: load database.
        # Structure is: domain,lockout_limit,user1,user1_count,user2,...
        # Use tabs instead of commas.
        # Lockout limit of 0 means unlimited.
        with open(lockout_filename, 'a+') as lf:
                lockout = lf.read().split('\n')
                lockout = list(filter(None, lockout)) # Remove newlines.
                for i in range(len(lockout)):
                    lockout[i] = lockout[i].split("\t")
                    for j in range(1,len(lockout[i]),2): lockout[i][j] = int(lockout[i][j])
        
        # Lockout protection: retrieve current target from database.
        lockout_entry = False
        lockout_entry_index = 0
        for lockout_entry_index in range(len(lockout)):
            if lockout[lockout_entry_index][0] == host:
                log("Found target in lockout database.")
                lockout_entry = lockout[lockout_entry_index]
                break
        
        # Lockout protection: not found? Let's create it!
        if not lockout_entry:
            lockout_entry_index = -1
            if lockout_limit == -1:
                log("No lockout limit supplied: using the default ("+str(lockout_limit_default)+").")
                lockout_limit = lockout_limit_default
            else:
                if lockout_limit == 0:
                    log("Account lockout protection disabled.")
                else:
                    log("Using lockout limit "+str(lockout_limit)+".")
            
            lockout_entry = [] # This will hold this run's data till we sync back to the db file.
            lockout_entry.append(host)
            lockout_entry.append(lockout_limit)
            for user in userlist:
                lockout_entry.append(user)
                lockout_entry.append(0)
        else:
            # Append any new users to the entry.
            for user in userlist:
                if not user in lockout_entry:
                    log("New user: " + user + ".") #info
                    lockout_entry.append(user)
                    lockout_entry.append(0)
            
            # Check lockout limit.
            if lockout_limit >= 0 and lockout_limit != lockout_entry[1]:
                if lockout_limit == 0:
                    error("Overriding previous account lockout limit for this host (was: "+str(lockout_entry[1])+"; now: disabled).\n")
                else:
                    error("Overriding previous account lockout limit for this host (was: "+str(lockout_entry[1])+"; now: "+str(lockout_limit)+").\n")
                lockout_entry[1] = lockout_limit
    
        # Array for keeping track.
        userlist_count = []
        for user in userlist:
            userlist_count.append(lockout_entry[lockout_entry.index(user)+1])
    
    # Baseline: Get request baseline if ping was not specified.
    if ping == None:
        # Let's get us a connexion.
        s = reconnect()
        
        # Request favicon with keep-alive.
        test_request = "HEAD /favicon.ico HTTP/1.0\nConnection: keep-alive\n\n"
        
        log("Testing baseline time.", True)
        
        baseline_results = [] # Hold multiple results.
        iterations = 10 # Number of iterations.
        
        while iterations > 0:
            try:
                iterations -= 1
                
                a = datetime.datetime.now()
                s.send(str.encode(test_request))
                reply = s.recv(4096)
                b = datetime.datetime.now()
                
                # Save.
                baseline_results.append((b-a).total_seconds() * 1000)
                
                if "close" in reply:
                    s = reconnect()
            except:
                s = reconnect()
        
        # Calculate mean and standard deviation.
        baseline_results = numpy.array(baseline_results)
        baseline = numpy.mean(baseline_results, axis=0)
        baseline_error = numpy.std(baseline_results, axis=0)
        
        log("Baseline (" + str(len(baseline_results)) + " iterations): " + str(baseline)[0:5] + " +- " + str(baseline_error)[0:5] + " ms\n", True)
        
        # Warn if baseline error is too high.
        if baseline_error/baseline > 0.3:
            if requestYN(Fore.RED+Style.BRIGHT+"[!] Warning: baseline error is high. Connection seems flakey. Continue anyway?"+Style.RESET_ALL, True) == False:
                print("")
                log("Exiting.", True)
                exit()
            print("")
        
        s.close()
    else:
        baseline = ping
        baseline_error = 0.1*ping
        log("Baseline (ping): " + str(baseline)[0:5] + " +- " + str(baseline_error)[0:5] + " ms\n")
    
    # Preload checks.
    if preload > 0:
        log("Preloading " + str(preload) + " connection" + plural(preload) + ".")
        i=0
        while i < preload:
            log("Connecting socket #"+str(i))
            reconnect(i)
            i += 1
        
    j=0
    J=reps
    limit_reps_for_standard_output = 10
    while j < J:
        
        if reps > 1 and verbose:
            log("Round "+str(j+1)+"...", True)
        
        j = j+1
        i = 0
        s = reconnect() # not used.
        
        while i < len(userlist):
            
            # Lockout protection.
            if not lockout_disable:
                # Check lockout count is less than limit.
                if userlist_count[i] >= lockout_entry[1] and lockout_entry[1] > 0:
                    #print("Lockout limit: " + str(lockout_entry[1]) + "\n")
                    # Only show above error message once.
                    if userlist[i] not in lockout_displayed_users:
                        error("Lockout limit reached for user " + userlist[i] + "!")
                        lockout_displayed_users.append(userlist[i])
                    # If the above confirmation failed:
                    # Add fake data?
                    x_values.append(i)
                    y_values.append(0.0001)
                    # Skip actual daq.
                    i += 1
                    continue
                
                # Increment lockout count for this user.
                userlist_count[i] += 1
            
            if preload>0:
                # Obtain handle to a socket.
                s = queue[preload_counter]
                
                # Increase preload counter and deal with overflow.
                preload_counter = (preload_counter + 1) % preload
            else:
                if i==0: s = reconnect()
            
            try:
                printnewline = False # Print newline after last user's username to clear the last line in the console.
                
                time.sleep(delay_between_requests) # For best results, make sure load on server is light?
                
                if verbose:
                    log(Fore.CYAN + "Testing user " + userlist[i] + Style.RESET_ALL)
                else:
                    sys.stdout.write(Fore.CYAN+'\r[-] Round ' + str(j) + '...' + userlist[i] + Style.RESET_ALL + ' ' * 20)
                    sys.stdout.flush()
                    if i == len(userlist) - 1:
                        printnewline = True
                        sys.stdout.write(Fore.CYAN+'\r[-] Round ' + str(j) + '...Done!' + Style.RESET_ALL + ' ' * 40) # Print the final newline after we know the response was quick.
                        sys.stdout.flush()
                
                req = build_request(userlist[i], filecontents)
                
                if showrequests:
                    print("\n"+str(req))
                
                (reply, y) = run_test(req, s, baseline)
                
                if showresponses:
                    print("\n"+str(reply))
                
                # Now print the newline.
                if reps <= limit_reps_for_standard_output and printnewline:
                    print("")
                    printnewline = False
                
                y_values.append(y)
                x_values.append(i)
                
                if not reply:
                    break
            except socket.timeout:
                error("Socket timed out!")
            except socket.error:
                error("Socket error!")
                print(m)
                # A bit of a hack.
                if preload>0:
                    reconnect(preload_counter)
                else:
                    s = reconnect()
                i = i-1
            except KeyboardInterrupt:
                print("\n\n[!] Interrupt detected. Quitting.")
                exit()
            
            if keepalive == False:
                # If we are preloading, reconnect this socket.
                if preload>0: reconnect(preload_counter)
                else: s = reconnect()
            i = i+1
            
        # Close after every round?
        if keepalive == False and preload == 0: s.close()
        
        # Don't reset preloads anymore.
        #if preload>0: queue = []

        results.append(y_values)
        y_values=[]
    if j < J: x_values=[]

    # Clean up.
    if preload>0:
        i=0
        while i < preload:
            try:
                queue[i].close()
            except:
                a = 0
            i += 1

    if not lockout_disable:
        # Lockout protection: update lockout_entry.
        for i in range(len(userlist)):
            # Find user in lockout_entry.
            idx = lockout_entry.index(userlist[i])
            # Update the lockout count.
            lockout_entry[idx+1] = userlist_count[i]
        
        # Lockout protection: merge lockout_entry into database.
        if lockout_entry_index == -1:
            lockout.append(lockout_entry)
        else:
            lockout[lockout_entry_index] = lockout_entry
        
        # Lockout protection: recompile to string.
        for x in range(len(lockout)):
            # Convert integers back to strings.
            for i in range(1,len(lockout[x]),2): lockout[x][i] = str(lockout[x][i])
            # Join to tab-separated.
            lockout[x] = '\t'.join(lockout[x])
        lockout = '\n'.join(lockout)
        
        # Lockout protection: write back to database file.
        with open(lockout_filename, "w") as lf:
            lf.write(lockout)
            log("Written lockout database.")

    # Calculate mean and standard deviation.
    res = numpy.array(results)
    
    ## Remove outliers here.
    # Regain handle to socket.
    preload_counter = 0
    queue = []
    if preload > 0:
        # Obtain handle to a socket.
        for i in range(preload): reconnect(i)
    else:
        s = reconnect()
        
    if outlier_threshold > 0. and lockout_disable is True and reps >= 4:
        max_retests = 3 * len(userlist)
        print("")
        first = True
        while True:
            changedSomething = False
            
            # Remove outliers, then re-run the tests until the arrays are filled once again.
            res = numpy.apply_along_axis(reject_outliers, axis=0, arr=res)
            
            if not verbose:
                if not first:
                    sys.stdout.write("\033[F")
                else:
                    first = False
            log('Retest count:  ' + str(rejected_outliers_count) + ' result' + ('' if rejected_outliers_count is 1 else 's') + ' so far.', True)
            
            # If there was an outlier, it will have the value 3.14159.
            itemindex = numpy.where(res==3.14159)
            for i in range(len(itemindex[0])):
            
                if preload>0:
                    # Obtain handle to a socket.
                    s = queue[preload_counter]
                    
                    # Increase preload counter and deal with overflow.
                    preload_counter = (preload_counter + 1) % preload
                
                user = userlist[itemindex[1][i]]
                time.sleep(delay_between_requests)
                
                req = build_request(user, filecontents)
                (reply, y) = run_test(req, s, baseline)
                
                log("Retesting user " + user + ": " + str(y)[:5] + "ms (old mean: " + str(res[itemindex[0][i]].mean())[:5] + "ms)")
                
                res[itemindex[0][i]][itemindex[1][i]] = y
                
                changedSomething = True
                max_retests = max_retests - 1
                
                if not verbose:
                    # Print live results table.
                    output_results(res)
                    # Go to top of table.
                    for i in range(0,int(9+reps)): sys.stdout.write("\033[1A" + Style.RESET_ALL)
                
                # If we are preloading, reconnect this socket.
                if preload>0: reconnect(preload_counter)
                else: s = reconnect()
                
            if changedSomething is False or max_retests <= 0:
                break
            
        if verbose:
            print("\n")
        else:
            sys.stdout.write("\033[F" + Style.RESET_ALL)
            sys.stdout.write("\033[F" + Style.RESET_ALL)
            sys.stdout.write("\033[K"+"\n"+"\033[K")
        log("Finished fixing outliers. Check the numbers in the last row as they may still be dodgy (retesting limited to three per user).", True)
    else:
        print("")
        log("Outlier removal disabled.", True)
    
    output_results(res)
    save_results(res)

def output_results(res):  
    global results,keepalive,userlist,x_values,y_values,preload,preload_counter,queue,withgraph,delay_between_requests
    global lockout_limit,lockout_disable,lockout_displayed_users,parameter,target,use_ssl,host,port,postdata,cookiedata,dont_urlencode,outlier_threshold,rejected_outliers_count
    
    mean = numpy.mean(res, axis=0)
    std = numpy.std(res, axis=0)
    #std = quadrature(std,baseline_error) # Combine errors in quadrature. No longer do this because it's pointless.
    pct = std*100/mean
    
    ## Output results.
    sys.stdout.write("\033[K")
    print("")
    sys.stdout.write("\033[K")
    log("All numbers below are in milliseconds.", True)
    sys.stdout.write("\033[K")
    
    # Calculate username lengths.
    min_width = 5 # Minimum column width.
    userlist_lengths = [max([max(len(x),min_width) for x in userlist])]*len(userlist) # Go with equal-spaced columns.
    userlist_lengths_total = 0
    for i in userlist_lengths: userlist_lengths_total += i
    
    sf = 5 # Significant figures for table data.
    spaces = 2
    dashes = "-"*(8 + userlist_lengths_total + (len(userlist) - 1) * spaces) # First column + names + spaces
    
    # Header row.
    i=0
    line = Fore.GREEN + Style.BRIGHT + "\nRound " + Fore.RESET + "| "
    while i<len(userlist):
        v = str(userlist[i])
        line += Fore.GREEN + Style.BRIGHT + v + " " * (userlist_lengths[i] - len(v) + spaces) + Fore.RESET
        i += 1
    print(line + Fore.RESET)
    print(dashes)
    
    # Raw data.
    i=0
    j=0
    results = res # Hack to reference updated results due to outliers.
    while j<len(results):
        # Round number.
        line = Fore.WHITE + Style.BRIGHT + str(j+1) + Fore.RESET + " "*(8-len(str(j+1))-2) + "| "
        i=0
        while i<len(results[j]):
            v = str(results[j][i])[:sf]
            line += Fore.WHITE + v + Fore.RESET + " " * (userlist_lengths[i] - len(v) + spaces)
            i += 1
        print(line)
        j += 1
    
    print(dashes)
    
    # Averages.
    line = Fore.GREEN + Style.BRIGHT + "Mean  " + Fore.RESET + "| "
    i=0
    while i<len(mean):
        v = str(mean[i])[:sf]
        line += Fore.MAGENTA + v + Fore.RESET + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print(line)
    line = Fore.GREEN + Style.BRIGHT + "Error " + Fore.RESET + "| "
    i=0
    while i<len(std):
        v = str(std[i])[:sf]
        line += Fore.MAGENTA + v + Fore.RESET + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print(line)
    line = Fore.GREEN + Style.BRIGHT + "% Err " + Fore.RESET + "| "
    i=0
    while i<len(pct):
        v = str(pct[i])[:sf]
        line += Fore.MAGENTA + v + Fore.RESET + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print(line)

def save_results(res):
    global results,keepalive,userlist,x_values,y_values,preload,preload_counter,queue,withgraph,delay_between_requests
    global lockout_limit,lockout_disable,lockout_displayed_users,parameter,target,use_ssl,host,port,postdata,cookiedata,dont_urlencode,outlier_threshold,rejected_outliers_count
    
    mean = numpy.mean(res, axis=0)
    std = numpy.std(res, axis=0)
    pct = std*100/mean
    
    # Save results of last run.
    of = [str(len(userlist)) + ',' + ','.join(userlist)]
    j=0
    while j<len(results):
        of.append(str(j+1) + ',' + ','.join([str(z) for z in numpy.array(results[j])]))
        j += 1
    csv = '\n'.join(of)
    
    fname = urlparse(target).hostname + "-" + time.strftime("%Y%m%d-%H.%M.%S") + ".csv"
    f = open(fname, 'w')
    f.truncate()
    f.write(csv)
    
	# Plot graph?
    if withgraph:
        try:
            # Try to open Excel.
            os.environ['opensesame'] = fname
            subprocess.Popen(['cmd','/C','start','adieu_graph_plotter.xlsm'], env=dict(os.environ))
        except:
            try:
                if len(userlist) == 2:
                    # Separate results.
                    valid = []
                    invalid = []
                    for rep in results:
                        valid.append(rep[0])
                        invalid.append(rep[1])
                    
                    validerr = numpy.array(valid).std()
                    invaliderr = numpy.array(invalid).std()
                    
                    # Plot.
                    plt.errorbar(range(1,len(results)+1), valid, yerr=validerr, label="Valid")
                    plt.errorbar(range(1,len(results)+1), invalid, yerr=validerr, label="Invalid")
                    plt.legend()
                else:
                    # Graph with errors.
                    plt.xticks(x_values[:len(userlist)], userlist)
                    plt.errorbar(x_values[:len(userlist)], mean, yerr=std)
                plt.show()
            except Exception as e:
                error("Could not plot graph =(.")
                print(e.args)
        
    # Output
    if outputfile != '':
        log("Generating " + outputfile)
        f = open(outputfile, 'w')
        f.truncate()
        f.write(csv)
        print("")
        log("File "+outputfile+" created.", True)

    return

# Runs a single check.
def run_test(req, s, baseline):
    reply = ""
    
    # TODO: This is a bit of a hack.
    req = req.replace("\n","\r\n")
    if sys.version_info[0] >= 3: reply = b''
    else: reply = ''
    
    a = datetime.datetime.now()
    s.send(str.encode(req))
    
    reply_part =  s.recv(4096)
    b = datetime.datetime.now() # Log traffic reception instantly.
    while reply_part: # Then actually read the response.
        reply = reply + reply_part
        reply_part =  s.recv(4096)
    
    y = (b-a).total_seconds() * 1000 - baseline
    
    return (reply, y)

def build_request(user, filecontents):
    global dont_urlencode, keepalive
    if not dont_urlencode:
        urlencoded = ""
        try:
            urlencoded = urllib.quote_plus(user)
        except:
            urlencoded = urllib.parse.quote_plus(user)
        req = filecontents.replace("???", urlencoded)
    else:
        req = filecontents.replace("???", user)

    # TODO: Improve this check for if it's a GET.
    if req.replace("GET /", "gubbins") != req or req.replace("HEAD /", "gubbins") != req:
        req = req + "\n\n"
    else:
        # Update content length.
        contentlen = req[req.find("\n\n")+2:].__len__()
        req = replaceHeader(req, "Content-Length", str(contentlen))
    
    # Keep alive?
    if keepalive:
        req = replaceHeader(req, "Connection", "keep-alive")
    
    return req

# Modified from: https://stackoverflow.com/a/45399188
'''
def reject_outliers_2(data, m = 6.):
    global rejected_outliers_count
    d = numpy.abs(data - numpy.median(data))
    mdev = numpy.median(d)
    s = d/(mdev if mdev else 1.)
    ret_data = data[s<m]
    rejected_outliers_count = rejected_outliers_count + data.shape[0] - ret_data.shape[0]
    return numpy.lib.pad(ret_data, (0,(data.shape[0]-ret_data.shape[0])), "constant",)
'''

# Because the data is heavily skewed, this takes a little more thought.
# It's relatively less likely for a result to be super quick, as the lower
# threshold for the round-trip time is pretty much fixed.
# However, it's fairly common for a packet to be misrouted and the resulting
# delay to be considerable, with the result that the mean is heavily distorted.
# The best option is to take percentiles, and then use some semi-empirical
# measure to form the accepted/rejected criterion.
def reject_outliers(data):
    global outlier_threshold, rejected_outliers_count
	
    lower_centile = 35
    upper_centile = 65
	
    while True:
        
        # Deduce the lower and upper percentiles.
        plower = numpy.percentile(data, lower_centile)
        pupper = numpy.percentile(data, upper_centile)
        
        # Take the middle group spanning the two percentiles and calculate the mean and standard deviation.
        middle = data[numpy.argwhere((data>=plower) & (data<=pupper))]
		
        if len(middle) is 0:
            lower_centile = lower_centile - 5
            upper_centile = upper_centile + 5
            #log("Moved centiles...", True)
            continue
		
        middlem = middle.mean()
        middles = middle.std()
        break
        
    
    # For each value, deduce the value relative to the standard deviation of the mean of the middle group.
    d = numpy.abs(data - middlem)
    s = d/(middles if middles else 1.)
    ret_data = data[s < outlier_threshold]
    rejected_outliers_count = rejected_outliers_count + data.shape[0] - ret_data.shape[0]
    return numpy.lib.pad(ret_data, (0,(data.shape[0]-ret_data.shape[0])), "constant", constant_values=(0.,3.14159))

# If preloading, n is the index in the queue array to reconnect.
def reconnect(n=-1):
    
    if n > preload: return False
    
    # Use ssl?
    if use_ssl:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s = ssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    s.connect((host, port))
    
    if preload > 0 and n!=-1:
        if len(queue) < preload:
            log("Creating socket #"+str(n))
            queue.append(s)
        else:
            log("Overwriting socket #"+str(n))
            queue[n] = s
    else:
        # Return a handle to this connexion.
        return s

def log(s,t=False):
    if t or verbose: print(Fore.CYAN+"[-] " + s + Fore.RESET)

def error(s):
    print("[!] " + s)

def plural(n):
    if n==1:
        return ""
    return "s"

# Request y or Y for True.
# Anything else is False.
# Unless second arg is specified as True.
def requestYN(question, defaultToYes=False):
    if not question: return False
    print(question),
    if defaultToYes: print("[Y/n] "),
    else: print("[y/n] "),
    answer = sys.stdin.read(1)
    if answer == "y" or answer == "Y": return True
    if answer == "\n" and defaultToYes: return True
    return False

# Combine errors in quadrature.
def quadrature(a,b):
    return pow(a*a+b*b, 0.5)

def replaceHeader(request, headerName, headerValue):
    # Assumes "HeaderName: headerValue\n" is the correct format.
    posn = request.lower().find(headerName.lower()) + len(headerName) + 2
    posnNL = request.find("\n", posn)
    return request[:posn] + headerValue + request[posnNL:]

def main(argv):
    global verbose,keepalive,withgraph,showrequests,showresponses,host,port,inputfile,outputfile,users,ping,reps
    global preload,delay_between_requests,lockout_limit,lockout_disable,parameter,target,cookiedata,postdata,dont_urlencode,outlier_threshold
    
    print(Fore.MAGENTA+Style.BRIGHT+"""
        (                 
     )  )\ ) (    (   (   
  ( /( (()/( )\  ))\ ))\  
  )(_)) ((_)|(_)/((_)((_) 
 ((_)_  _| | (_|_))(_))(  
 / _) / _) | | / -_) || | 
 \__,_\__,_| |_\___|\_,_| 
 """+Style.RESET_ALL)
    
    
    try:
        opts, args = getopt.getopt(argv,"hvki:o:u:t:p:P:r:n:l:",
                                   ["help","verbose","keep-alive","with-graph","delay=",
                                    "outlier-threshold=","requests","responses","request=","users=","csv=",
                                    "target=","ping=","reps=","preload=","lockout=",
                                    "no-lockout","ignore-lockout","parameter=","postdata=","cookiedata=","no-encoding"])
    except getopt.GetoptError:
        print('Unrecognized option. Try '+Fore.MAGENTA+Style.BRIGHT+'python ./adieu.py --help'+Style.RESET_ALL+' for a full list.')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h','--help'):
            helptext()
            sys.exit()
        elif opt in ("-k", "--keep-alive"):
            keepalive = True
        elif opt == "--requests":
            showrequests = True
        elif opt == "--responses":
            showresponses = True
        elif opt == "--delay":
            delay_between_requests = float(arg)/1000
        elif opt == "--postdata":
            postdata = arg
        elif opt == "--cookiedata":
            cookiedata = arg
        elif opt == "--with-graph":
            withgraph = True
        elif opt in ("-v", "--verbose"):
            verbose = True
        elif opt in ("-i", "--request"):
            inputfile = arg
        elif opt in ("-o", "--csv"):
            outputfile = arg
        elif opt in ("-u", "--users"):
            users = arg
        elif opt in ("-t", "--target"):
            target = arg
        elif opt in ("-P", "--ping"):
            ping = float(arg)
        elif opt in ("-p", "--parameter"):
            parameter = arg
        elif opt in ("-r", "--reps"):
            reps = float(arg)
        elif opt in ("-l", "--lockout"):
            lockout_limit = int(arg)
        elif opt == "--no-lockout" or opt == "--ignore-lockout":
            lockout_disable = True
        elif opt in ("-n", "--preload"):
            preload = int(arg)
        elif opt == "--no-encoding":
            dont_urlencode = True
        elif opt == "--outlier-threshold":
            if int(arg) <= 0:
                outlier_threshold = 0
            else:
                outlier_threshold = int(arg)

    if len(sys.argv) == 1:
            helptext()
            sys.exit()
    else:
        client()

# Make s bold.
def b(s):
    return Style.BRIGHT + s + Style.RESET_ALL
# Make blue-bold:
def bl(s):
    return Fore.BLUE + Style.BRIGHT + s + Style.RESET_ALL
# Make purple:
def p(s):
    return Fore.MAGENTA + Style.BRIGHT + s + Style.RESET_ALL
        
# Make s bold.
def b(s):
    return Style.BRIGHT + s + Style.RESET_ALL
# Make blue-bold:
def bl(s):
    return Fore.BLUE + Style.BRIGHT + s + Style.RESET_ALL
# Make purple:
def p(s):
    return Fore.MAGENTA + Style.BRIGHT + s + Style.RESET_ALL

def helptext():
    print(" adieu discovers app users\r\n   based on time delays\n")
    
    print(Fore.MAGENTA+Style.BRIGHT+"\t$ python ./adieu.py --target= --users= "+bl("[")+p(" --postdata= ")+bl("OR")+Fore.MAGENTA+Style.BRIGHT+" --request= "+bl("]")+p(" ...\n")+Style.RESET_ALL)
    
    print(Fore.BLUE+Style.BRIGHT+"Required parameters:"+Style.RESET_ALL+" ("+b("b")+"old indicates short option)")
    
    options1 = [
               ["--"+b("t")+"arget=",         "Target, e.g. https://timebased.ninja:8443/login.php."],
               ["--"+b("u")+"sers=",          "File with one username per line, or colon-separated usernames."],
               ["--postdata=",          "Post data. Specify parameter using a well-placed '???' and adieu will build the request "+bl("..OR..")],
               ["-i,--request=",        "File containing raw HTTP request. Replace the parameter with '???', or use --parameter=myparam."],
#               ["-p,--parameter=",      "The parameter to cycle through, e.g. username."],
               ]
    options2 = [
               ["--"+b("h")+"elp      ",            "This text."],
               ["--cookiedata=",        "Cookie data to include in requests."],
               ["--"+b("r")+"eps=   ",           "Number of repetitions/iterations to perform. Generally, more is better, but watch out for account lockouts."],
               ["--"+b("k")+"eep-alive",      "Set Connection: Keep-Alive on outgoing requests (can improve reliability, speed, and accuracy)."],
               ["-n,--preload=",        "To reduce systematic error, preload this many connections and store them in a round-robin-type queue."],
               ["--"+b("l")+"ockout=",        "Max attempts per user to avoid locking accounts. -l 0 sets to infinity, but still keeps track of requests (default=3)."],
               ["--ignore-lockout",         Fore.RED+b("[!Risky!]")+" Use if you aren't concerned about locking accounts out."],
               ["-o,--csv=",            "Output the results as a CSV for importing into Excel."],
               ["-P,--ping=",           "Specify the average ping delay (ms) between you and the target. The default is to HEAD favicon.ico 10 times. Disable this with --ping=0."],
               ["--"+b("v")+"erbose",         "Show verbose logging."],
               ["--with-graph",         "Show a matplotlib or Excel graph of results, if available."],
               ["--delay=",             "Sleep ms between requests."],
               ["--no-encoding",        "Don't URL encode payloads."],
               ["--outlier-threshold=",  "Tolerance for accepting a result. The default is 5. It is enabled only if --ignore-lockout and --reps >= 4. To disable, set to zero."],
               ["--requests",           "(Debugging) Print requests."],
               ["--responses",          "(Debugging) Print responses."]
              ]
    
    for i in options1:
        if "request" in i[0]:
            print("\t" + i[0] + "\t\t" + i[1])
        else:
            print("\t" + i[0] + "\t\t" + i[1])
    print(Fore.BLUE+Style.BRIGHT+"\nOptional parameters:"+Style.RESET_ALL)
    
    for i in options2:
        if "ignore" in i[0] or "threshold" in i[0]:
            print("\t" + i[0] + "\t" + i[1])
        else:
            print("\t" + i[0] + "\t\t" + i[1])
        
    print("")
    
    print(Fore.BLUE+Style.BRIGHT+"Example usage:"+Style.RESET_ALL)
    print("\tTest whether app is vulnerable using post data:")
    print(Fore.MAGENTA+Style.BRIGHT+"\t\tpython ./adieu.py --target=https://test.server/adieuTest.php -u \"jeremy:matt\" --postdata=\"user=???&pass=badPass\" --ignore-lockout --reps=3 --csv=out1.csv"+Style.RESET_ALL)
    print("")
    print("\tDiscover other users using a request file:")
    print(Fore.MAGENTA+Style.BRIGHT+"\t\tpython ./adieu.py -i adieuRequest.txt --target=https://test.server -u \"barry:admin:jeremy:matt:jim\" --ignore-lockout --reps=3 --with-graph --csv=out2.csv"+Style.RESET_ALL)
    print("")

if __name__ == "__main__":
   main(sys.argv[1:])
