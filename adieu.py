import socket
import time
from urlparse import urlparse
import datetime
import ssl
import sys, getopt
import numpy
try: import matplotlib.pyplot as plt
except: print "[!] Install MatPlotLib to visualize the tool's output.\n"

numpy.set_printoptions(precision=3) # Numpy decimal places.

# Define some global variables. (Probably not the most elegant way).
inputfile = ''
outputfile = ''
host = ''
port = 80
use_ssl = False
target = "" # The target host.
ping = None
parameter = "user" # Parameter in the POST request file to cycle through.
reps = 1 # Number of cycles.
preload = 0 # Number of connexions to pre-open.
keepalive = False # Set request Connection header to hold socket open.
showrequests = False # Print requests.
showresponses = False # Print server responses.
verbose = False # Print all logged info.
users = '' # Either valid:invalid or a \n-separated list.
withgraph = False # Plot graph on linux.
delay_between_requests = 0.1 # Sleep between requests.

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
    global keepalive,userlist,x_values,y_values,preload,preload_counter,queue,withgraph,delay_between_requests,lockout_limit,lockout_disable,lockout_displayed_users,parameter,target,use_ssl,host,port
    
    baseline_error = 0.0
    
    if inputfile is '':
        error("No input file specified.")
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
    userlist = filter(None, userlist)
        
    if len(userlist) < 2:
        error("Need at least two users.")
        exit()

    with open(inputfile, 'r') as f:
        filecontents = f.read().replace("\r\n", "\n").rstrip('\n')
        parameters = filecontents.split('\n\n', 1)[-1].split('&')
        
        for i in parameters:
            args = i.split('=')
            if args[0] == parameter:
                filecontents = filecontents.replace(i, args[0] + "=" + "%PLACEHOLDER")
        
        if not "%PLACEHOLDER" in filecontents:
            error("Unable to locate parameter '" + parameter + "'.")
            if verbose:
                print "\nFull request:\n------------\n"
                print filecontents + "\n"
            exit()
    
    ## Parse the target.
    target_parsed = urlparse(target)
    port = target_parsed.port
    host = target_parsed.netloc.split(":")[0]
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
        print "No host specified."
        exit()
    if port is 0 or port is None:
        print "No port specified."
    
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
                lockout = filter(None, lockout) # Remove newlines.
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
                log("No lockout limit supplied: using the default ("+`lockout_limit_default`+").")
                lockout_limit = lockout_limit_default
            else:
                if lockout_limit == 0:
                    log("Account lockout protection disabled.")
                else:
                    log("Using lockout limit "+`lockout_limit`+".")
            
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
                    error("Overriding previous account lockout limit for this host (was: "+`lockout_entry[1]`+"; now: disabled).\n")
                else:
                    error("Overriding previous account lockout limit for this host (was: "+`lockout_entry[1]`+"; now: "+`lockout_limit`+").\n")
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
                s.send(test_request)
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
        
        log("Baseline (" + `len(baseline_results)` + " iterations): " + `baseline`[0:5] + " +- " + `baseline_error`[0:5] + " ms\n", True)
        
        # Warn if baseline error is too high.
        if baseline_error/baseline > 0.3:
            if requestYN("[!] Warning: baseline error is high. Connection seems flakey. Continue anyway?", True) == False:
                print ""
                log("Exiting.", True)
                exit()
            print ""
        
        s.close()
    else:
        baseline = ping
        baseline_error = 0.1*ping
        log("Baseline (ping): " + `baseline`[0:5] + " +- " + `baseline_error`[0:5] + " ms\n")
    
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
                    #print "Lockout limit: " + `lockout_entry[1]` + "\n"
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
                    log("Testing user " + userlist[i])
                else:
                    sys.stdout.write('\r[-] Round ' + `j` + '...' + userlist[i] + ' ' * 20)
                    sys.stdout.flush()
                    if i == len(userlist) - 1:
                        printnewline = True
                        sys.stdout.write('\r[-] Round ' + `j` + '...Done!' + ' ' * 40) # Print the final newline after we know the response was quick.
                        sys.stdout.flush()
                    
                req = filecontents.replace("%PLACEHOLDER", userlist[i])

                # Update content length.
                length = req[req.find("\n\n")+2:].__len__() - 1
                req = replaceHeader(req, "Content-Length", `length`)
                
                if showrequests:
                    print req
                
                # Keep alive?
                if keepalive:
                    req = replaceHeader(req, "Connection", "keep-alive")

                a = datetime.datetime.now()
                s.send(req)
                reply = s.recv(4096)
                
                b = datetime.datetime.now()
                y = (b-a).total_seconds() * 1000 - baseline
                
                if showresponses:
                    print reply
                
                # Bit of a hack for if the response time is massive (4 * baseline).
                if (b-a).total_seconds() * 1000 > 50 * baseline and baseline > 10:
                    log("Oops! Reponse took too long, retrying.") # Probably dodgy network error somewhere. It happens...
                    i = i - 1
                    # Clear the line.
                    if i == len(userlist) - 1:
                        print '\r'
                else:
                    # Now print the newline.
                    if reps <= limit_reps_for_standard_output and printnewline:
                        print ""
                        printnewline = False
                    y_values.append(y)
                    x_values.append(i)
                if not reply:
                    break
            except socket.timeout, m:
                error("Socket timed out!")
            except socket.error, m:
                error("Socket error!")
                print m
                # A bit of a hack.
                if preload>0:
                    reconnect(preload_counter)
                else:
                    s = reconnect()
                i = i-1
            except KeyboardInterrupt:
                print "\n\n[!] Interrupt detected. Quitting."
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
        if j<J: x_values=[]

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
            for i in range(1,len(lockout[x]),2): lockout[x][i] = `lockout[x][i]`
            # Join to tab-separated.
            lockout[x] = '\t'.join(lockout[x])
        lockout = '\n'.join(lockout)
        
        # Lockout protection: write back to database file.
        with open(lockout_filename, "w") as lf:
            lf.write(lockout)
            log("Written lockout database.")

    # Calculate mean and standard deviation.
    res = numpy.array(results)
    mean = numpy.mean(res, axis=0)
    std = numpy.std(res, axis=0)
    #std = quadrature(std,baseline_error) # Combine errors in quadrature. No longer do this because it's pointless.
    pct = std*100/mean
    
    ## Output results.
    
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
    line="\n\nRound | "
    while i<len(userlist):
        v = str(userlist[i])
        line += v + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print line
    print dashes
    
    # Raw data.
    i=0
    j=0
    while j<len(results):
        line=str(j+1) + " "*(8-len(str(j+1))-2) + "| "
        i=0
        while i<len(results[j]):
            v = str(results[j][i])[:sf]
            line += v + " " * (userlist_lengths[i] - len(v) + spaces)
            i += 1
        print line
        j += 1
    
    print dashes
    
    # Averages.
    line = "Mean  | "
    i=0
    while i<len(mean):
        v = str(mean[i])[:sf]
        line += v + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print line
    line = "Error | "
    i=0
    while i<len(std):
        v = str(std[i])[:sf]
        line += v + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print line
    line = "% Err | "
    i=0
    while i<len(pct):
        v = str(pct[i])[:sf]
        line += v + " " * (userlist_lengths[i] - len(v) + spaces)
        i += 1
    print line
    
    if withgraph:
        try:
            if len(userlist) == 2:
                # Separate results.
                valid = []
                invalid = []
                for rep in results:
                    valid.append(rep[0])
                    invalid.append(rep[1])
                
                # Plot.
                plt.plot(range(1,len(results)+1), valid)
                plt.plot(range(1,len(results)+1), invalid)
            else:
                # Graph with errors.
                plt.xticks(x_values, userlist)
                plt.errorbar(x_values, mean, yerr=std)
                plt.xticks(x_values, userlist)
            plt.show()
        except:
            error("Could not plot graph =(.")
        
    # Save results of last run.
    of = [`(len(userlist))` + ',' + ','.join(userlist)]
    j=0
    while j<len(results):
        of.append(str(j+1) + ',' + ','.join([str(z) for z in numpy.array(results[j])]))
        j += 1
    csv = '\n'.join(of)
    
    f = open("lastrun.csv", 'w')
    f.truncate()
    f.write(csv)
        
    # Output
    if outputfile != '':
        log("Generating " + outputfile + ".csv")
        f = open(outputfile+".csv", 'w')
        f.truncate()
        f.write(csv)
        
        log("File "+outputfile+".csv created.", True)

    return

# If preloading, n is the index in the queue array to reconnect.
def reconnect(n=-1):
    # Use ssl?
    if use_ssl:
        log("Using TLS.")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s = ssl.wrap_socket(sock, cert_reqs=ssl.CERT_NONE)
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    s.connect((host, port))
    
    if preload > 0 and n!=-1:
        if len(queue) < preload:
            #log("Creating socket #"+str(n))
            queue.append(s)
        else:
            #log("Overwriting socket #"+str(n))
            queue[n] = s
    else:
        # Return a handle to this connexion.
        return s

def log(s,t=False):
    if t or verbose: print "[-] " + s

def error(s):
    print "[!] " + s

def plural(n):
    if n==1:
        return ""
    return "s"

# Request y or Y for True.
# Anything else is False.
# Unless second arg is specified as True.
def requestYN(question, defaultToYes=False):
    if not question: return False
    print question,
    if defaultToYes: print "[Y/n] ",
    else: print "[y/n] ",
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
    global verbose,keepalive,withgraph,showrequests,showresponses,host,port,inputfile,outputfile,users,ping,reps,preload,delay_between_requests,lockout_limit,lockout_disable,parameter,target
    
    print """
       (                 
    )  )\ ) (    (   (   
 ( /( (()/( )\  ))\ ))\  
 )(_)) ((_)|(_)/((_)((_) 
((_)_  _| | (_|_))(_))(  
/ _` / _` | | / -_) || | 
\__,_\__,_| |_\___|\_,_| 
                         
"""
    
    
    try:
        opts, args = getopt.getopt(argv,"hvki:o:u:t:p:P:r:n:l:",
                                   ["help","verbose","keep-alive","with-graph","delay=","requests","responses","request=","users=","csv=","target=","ping=","reps=", "preload=", "lockout=", "no-lockout", "parameter="])
    except getopt.GetoptError:
        print 'Usage:\n\tadieu.py -i <request file> -u <users> -t <target> -p <parameter> ...'
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
        elif opt == "--no-lockout":
            lockout_disable = True
        elif opt in ("-n", "--preload"):
            preload = int(arg)
    
    client()

def helptext():
    print "adieu is a time-based user enumerator.\n"
    
    print "python ./adieu.py ...\n"
    
    print "Options:"
    
    options = [
               ["-h,--help",            "This text."],
               ["-t,--target=",         "Target, e.g. timebased.ninja:443."],
               ["-p,--parameter=",      "The parameter to cycle through, e.g. username."],
               ["-i,--request=",        "File containing request, e.g. from Burp."],
               ["-u,--users=",          "File with one username per line, or colon-separated usernames."],
               ["-r,--reps=",           "(Optional) Number of repetitions/iterations to perform. Generally, more is better, but watch out for account lockouts."],
               ["-k,--keep-alive",      "(Optional) Set Connection: Keep-Alive on outgoing requests (can improve reliability, speed, and accuracy)."],
               ["-n,--preload=",        "(Optional) To reduce systematic error, preload this many connections and store them in a round-robin-type queue."],
               ["-l,--lockout=",        "(Optional) For login forms: Max number of attempts per user to avoid account lockouts. --lockout=0 sets to infinity, but still tracks requests (default=3)."],
               ["--no-lockout",         "(Optional) For forgotten password forms etc: Do not track requests."],
               ["-o,--csv=",            "(Optional) Output the results as a CSV for importing into Excel."],
               ["-P,--ping=",           "(Optional) Specify the average ping delay (ms) between you and the target. The default is to HEAD favicon.ico 10 times. Disable this with --ping=0."],
               ["-v,--verbose",         "(Optional) Show verbose logging."],
               ["--with-graph",         "(Optional) Show a matplotlib graph of results, if available."],
               ["--delay=",             "(Optional) Sleep ms between requests."],
               ["--requests",           "(Debugging) Print requests."],
               ["--responses",          "(Debugging) Print responses."]
              ]
    
    for i in options:
        print "\t" + i[0] + "\t\t" + i[1]

if __name__ == "__main__":
   main(sys.argv[1:])
