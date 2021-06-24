import os
import sys
import csv
import subprocess32 as subprocess
import multiprocessing
import time
import psutil
import signal
from threading import Thread, Timer
import Queue
import resource
import shutil
import datetime
import random
import math
import re

AT_FILE="@@"

def error_msg(s):
    print bcolors.FAIL+"[ERROR] {0}".format(s)+bcolors.ENDC
    # sys.exit()
    
def warning_msg(s):
    print bcolors.WARNING+"[ERROR] {0}".format(s)+bcolors.ENDC

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log2(x):
    return math.log(x,2)

def terminate_proc_tree(pid, include_parent = False):
    """
    kill the process tree of the given pid, it is
    possible the pid does not exist, so we need to be
    robust catching the execption instead of simply crashing
    """
    try:
        p = psutil.Process(pid)
        for child in p.children(recursive=True):
            os.kill(child.pid, signal.SIGABRT)
        if include_parent:
            p.kill()
    except Exception:
        pass

def mkdir(dirp):
    if not os.path.exists(dirp):
        os.makedirs(dirp)

def mkdir_force(abs_dir):
    """
    create new dir, rm the old one if exists
    """
    if os.path.exists(abs_dir):
        print ['rm', '-rf', abs_dir]
        subprocess.Popen(['rm', '-rf', abs_dir]).wait()
    os.makedirs(abs_dir)

def rmfile_force(abs_path, silent=False):
    """
    create new file, rm the old one if exists
    """
    if os.path.exists(abs_path):
        if not silent:
            print ['rm', abs_path]
        subprocess.Popen(['rm', abs_path]).wait()

def count_children(folder, key):
    """
    iteratively trace the descendents of seeds with `key` in its name
    """
    seeds = [f for f in os.listdir(folder) if \
             os.path.isfile(os.path.join(folder, f))]
    key_wq = [key]
    result = set()
    while len(key_wq) != 0:
        _k = key_wq.pop(0)
        for seed in seeds:
           _id = seed.split(",")[0].strip("id:")
           _src = seed.split(",")[1].strip("sync:").strip("src:")
           if _k in _src:
               # find the children of _id
               key_wq.append(_id)
               # record _id as a children
               result.add(_id)
    return len(result)

def update_raw_coverage(raw, csv_file_name, debug=False):
    with open(csv_file_name) as csv_file:
        reader = csv.DictReader(csv_file, delimiter='\t')
        counter =0 
        for row in reader:
            e = row['edge_id']
            if debug and counter < 50:
                #print the top 50 rows
                print row, e
                counter+=1
            if e not in raw:
                raw[e] = { 
                    'inputs': row['inputs'], 
                    'seeds': row['seeds'],
                    'first_seen': row['first_seen']
                }
            else:
                try:
                    r = row['inputs']
                    s = row['seeds']
                    raw[e]['inputs'] += r
                    raw[e]['seeds'] += s
                except TypeError:
                    print r
                    print s
                    print raw[e]


def update_raw_sanitizer(raw, csv_file_name):
    with open(csv_file_name) as csv_file:
        reader = csv.DictReader(csv_file, delimiter='\t')
        for row in reader:
            e = row['edge_id']
            if e not in raw:
                raw[e] = {
                    'first_seen': row['first_seen']
                }

def merge_sanitizer_files(data_files, output_name):
    raw_data = dict()
    try:
        with open(output_name, 'w') as final_f:
            for file_name in data_files:
                update_raw_sanitizer(raw_data, file_name)
            field_names = ['edge_id', 'first_seen']
            writer = csv.DictWriter(final_f, fieldnames=field_names, delimiter='\t')
            writer.writeheader()
            for edge, raw in raw_data.iteritems():
                tmp=dict()
                tmp['edge_id']=edge
                tmp['first_seen']=raw['first_seen']
                writer.writerow(tmp)
            final_f.close()
            return True
    except Exception:
        print data_files
        warning_msg("can not create merged sanitizer file {0}".format(output_name))
        return False

def append_merge_coverage_files(data_files, output_name):
    covered_edges = dict()
    try:
        if (os.path.exists(output_name)):
            with open(output_name, 'r') as final_f:
                lines = final_f.readlines()
                for _ in lines:
                    if "," in _:
                        # have context.
                        edge = int(_.split(",")[0].strip())
                        bits = int(_.split(",")[1].strip())
                        if not covered_edges.has_key(edge):
                            covered_edges[edge] = bits
                        else:
                            covered_edges[edge] &= (bits & 0xff)
                    else:
                        covered_edges[edge] = 1

                print 'before appending ', len(covered_edges)
        for file_name in data_files:
            with open(file_name, 'r') as f:
                lines = f.readlines()
                for _ in lines:
                    if ',' in _:
                        edge = int(_.split(",")[0].strip())
                        bits = int(_.split(",")[1].strip())
                        # print "read ", edge, "bits: ",bits
                        if not covered_edges.has_key(edge):
                            covered_edges[edge] = bits
                        else:
                            covered_edges[edge] &= (bits & 0xff)
                    else:
                        covered_edges[edge] = 1
            # os.unlink(file_name)
        print 'after appending ', len(covered_edges)
        # print covered_edges
        with open(output_name, 'w+') as final_f:
            for k,v in covered_edges.iteritems():
                # print "coordinator writing ", k, ",",str(v)
                final_f.write(str(k)+','+str(v)+'\n')
        return True
    except IOError:
        print data_files
        warning_msg("can not apend new merge coverage files{0}".format(output_name))
        return False

def merge_coverage_files(data_files, output_name, ftype='branch-only'):
    raw_data = dict()
    covered_edges = set()
    try:
        if ftype == 'branch-only':
            with open(output_name, 'r') as final_f:
                covered_edges = covered_edges | set([_.strip() for _ in final_f.readlines()])
    except Exception:
        pass

    for f in data_files:
        if not os.path.exists(f):
            print "fuzzer cov files not exists: {0}".format(f)
            return False
    try:
        with open(output_name, 'w+') as final_f:
            for file_name in data_files:
                update_raw_coverage(raw_data, file_name)
            if ftype == 'csv':
                field_names = ['edge_id', 'inputs', 'seeds', 'first_seen']
                writer = csv.DictWriter(final_f, fieldnames=field_names, delimiter='\t')
                writer.writeheader()
                for edge, raw in raw_data.iteritems():
                    #exclude the total execution row
                    if edge == '0':
                        continue
                    tmp=dict()
                    tmp['edge_id']=edge
                    tmp['inputs']=raw_data[edge]['inputs']
                    tmp['seeds']=raw_data[edge]['seeds']
                    tmp['first_seen']=raw_data[edge]['first_seen']
                    writer.writerow(tmp)
            if ftype == 'branch-only':
                e_set = covered_edges | set([edge for edge, raw in raw_data.iteritems()])
                final_f.write('\n'.join(list(e_set)))
            final_f.close()
            return True
    except Exception:
        print data_files
        warning_msg("can not merge coverage file {0}".format(output_name))
        return False


def expand_stack_limit():
    """Klee requires ulimit to set stack as unlimited"""
    resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))

def loop_every(period, func, args = None):
    """
    Synchronizly execute the given function
    This is a None-return function, only terminate when ctrl-c is hit
    """
    while True:
        time.sleep(period)
        if not args:
            func();
        else:
            func(args)

def exec_sync(cmd, mock_eof=False, working_dir=None, env=None, use_shell=False, mem_cap=None):
    fin = None
    if mock_eof:
        fin=open(os.devnull)
    if env is not None:
        os.environ=env
    if mem_cap is not None:
        cmd = ["ulimit -v " + mem_cap + ";"] + cmd
    subprocess.call(cmd, shell=use_shell, stdin=fin)

def signal_ignore(arg1, arg2):
    os._exit(0)

def exec_async(cmd, mock_eof=False, working_dir=None, use_shell=False, env=None, no_output=False, mem_cap=None):
    fin = None
    fout = None
    if mock_eof:
        fin=open(os.devnull)

    if no_output:
        fout=open(os.devnull)

    if env is not None:
        os.environ=env

    if mem_cap is not None:
        cmd = ["ulimit -v " + mem_cap + ";"] + cmd

    if use_shell:
        cmd = ' '.join(cmd)

    p = subprocess.Popen(cmd, shell=use_shell, stdin=fin, stdout=fout)
    p.wait();

def qsym_exec_async(cmd, stdin=None, use_shell=False, env=None, no_output=False, mem_cap=None, testcase_dir=None):
    print "Running utils.qsym_exec_async!"
    fout = None

    if env is not None:
        os.environ=env

    if mem_cap is not None:
        cmd = ["ulimit -v " + mem_cap + ";"] + cmd

    if use_shell:
        cmd = ' '.join(cmd)
    cmddocker = "docker run -i --privileged --user root -v /home/tk/work/muse/jpeg:/root/work/muse/jpeg "
    if testcase_dir is not None:
        cmddocker += "-v " + testcase_dir + ":" + testcase_dir
    cmddocker += " zjuchenyuan/qsym:latest /bin/bash -c \'" + cmd + "\'"
    print "Running qsym with command: " + cmddocker
    p = subprocess.Popen(cmddocker, shell=use_shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #output = p.communicate(stdin)
    output = p.communicate()
    p.wait()
    print "utils.qsym exec async finished!"

def remove_dup(orig_f, new_f):
    cmd = ["sort", orig_f, "|" , "uniq", ">", new_f]
    cmd = " ".join(cmd)
    subprocess.call(cmd, shell=True)
    if os.path.isfile(new_f):
        return True
    else:
        return False

# read file `f` and count number of lines if `with_weight` is False,
# otherwise add up the number at each line.
def count_file_items(f, with_weight):
    res = 0
    try:
        with open(f, "r") as inf:
            nums = inf.readlines()
            if with_weight:
                res = sum([int(x) for x in nums])
            else:
                res = len(nums)
    except Exception:
        error_msg("count file error, return 0")
        res = 0
    return res

# read file `f` and collect the id of each line, if `union` is Flase,
# into a set. Otherwise collect ids into a list.
def collect_file_items(f, union=False):
    res = set() if union else list()
    with open(f, "r") as inf:
        ids = inf.readlines()
        for id in ids:
            if union:
                res.add(id)
            else:
                res.append(id)
    return res




# Generate edges covered by input seed
def gen_loctrace_file(prog, inp, input_mode,outfile=None, timeout=0.2):

    if prog is None or inp is None:
        return False
    myenv = os.environ.copy()
    #be careful as the prog might contain extra cmd line options
    target_file = os.path.dirname(os.path.abspath(prog).split()[0])+'/loctrace.csv.'+str(random.randint(1,10000000))
    if outfile is not None:
        target_file = outfile
        if os.path.exists(target_file):
            os.unlink(target_file)
    myenv['AFL_LOC_TRACE_FILE'] = target_file
    if "@@" in prog.split():
        prog_cmd = prog.replace("@@", inp)
    else:
        prog_cmd = " ".join([prog + " < " + inp])
    prog_cmd = "timeout " + str(timeout)+"s " + prog_cmd
    prog_cmd = prog_cmd + " > /dev/null 2> /dev/null"
    p = subprocess.Popen(prog_cmd, shell=True, env=myenv)
    p.wait()
    if os.path.exists(target_file):
        return True
    else:
        return False

def run_one_with_envs(prog, inp, input_mode, envs, timeout=0.2, from_moriarty=False):
    my_envs = os.environ.copy()
    for e in envs:
        my_envs[e] = envs[e]
    if "@@" in prog.split():
        prog_cmd = prog.replace("@@", inp)
    else:
        prog_cmd = " ".join([prog + " < " + inp])
    prog_cmd = "timeout " + " -s ABRT -k " + str(timeout + 1) + " " + str(timeout)+"s " + prog_cmd
    prog_cmd = prog_cmd + " > /dev/null 2> /dev/null"
    print "run one: ",prog_cmd, " #from moriarty" if from_moriarty else " #from meuzz" 
    sys.stdout.flush()
    # p = subprocess.Popen(prog_cmd, shell=True, env=my_envs)
    p = subprocess.call(prog_cmd, shell=True, env=my_envs, timeout=10.0)
    print "Runone done"
    sys.stdout.flush()


def get_edge_cover_by_seed(prog_cmd, seed, input_mode):
    edges = []
    file_name = "/tmp/.loctracetmp"+str(random.randint(1,100000))
    if not gen_loctrace_file(prog_cmd, seed, input_mode, file_name):
        error_msg("Unable to generate loc trace file with cmd {0} and seed {1}".format(prog_cmd, seed))
    if os.path.exists(file_name):
        with open(file_name, "r") as f:
            for l in f.readlines():
                try:
                    edges.append(l.split(",")[1].strip())
                except Exception:
                    continue
        os.unlink(file_name)

    return edges

def read_edges_from_file(file_name):
    edges = []
    if os.path.exists(file_name):
        with open(file_name, "r") as f:
            for l in f.readlines():
                try:
                    edges.append(l.split(",")[1].strip())
                except Exception:
                    continue
    return edges

def log_recommend_edges(lst, log, loc_map, find_loc_script, prog, cur_heu):
    """
    Automatically record the source locations of the recommended edges
       lst is the return of find_edges_for_SE
       log is the output file
       loc_map is generated in the sefuzz compilation directory
       find_loc_script is under afl/afl-2.39b/
    """


    if log is None:
        return

    def _get_src_loc(e, s):
        cmd = [find_loc_script, e, loc_map, prog + " < " + s]
        cmd = " ".join(cmd)
        #we call the find script twice, first to get loctrace, second to get src
        subprocess.call(cmd, shell=True)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        out, err = p.communicate()
        return out

    with open(log, 'a') as log_f:
        for record in lst:
            edges = record["interesting_edges"]
            inp   = record["input"]
            for _e in edges:
                src = _get_src_loc(_e, inp)
                if len(src) > 0: 
                    log_f.write(cur_heu+"\t"+src+'\n')
            # map(lambda e: log_f.write(prefix + _get_src_loc(e, inp)+'\n'), edges)
    log_f.close()


def add_file_snag(filename, snag='--------snag--------'):
    try:
        with open(filename, 'a') as f:
            f.write('\n'+snag+'\n')
        f.close()
    except Exception:
        pass




def compile_target(proj_dir, compile_script):
    """
    invoke the target compile script to build afl-binary and klee-bitcode
    This call is BLOCKING, because we want to wait until the compilation finish
    """
    try:
        subprocess.Popen(os.path.join(proj_dir, compile_script), cwd=proj_dir).wait()
    except Exception:
#        error_msg("Error: did you specify the absolute path of the project?")
        pass


def save_inputs(seed_list, target_dir):
    if not os.path.isdir(target_dir):
        error_msg("{0} is not a valid directory".format(target_dir))
        return
    for seed in seed_list:
        shutil.copy2(seed['input'], target_dir)

def pack_klee_errors(search_dir, target_dir):
    """
    Remove all klee-out dirs without klee error outputs
    and then pack all the rest into a specified output dir
    """
    #create target_dir is not existed
    if not os.path.exists(target_dir):
        os.mkdir(target_dir)

    #make dir base on date time
    now = datetime.datetime.now()
    subdir = target_dir+"/"+now.strftime("%Y-%m-%d-%H:%M")
    uniq_num=0
    try:
        os.mkdir(subdir)
    except Exception:
        pass
    

    def has_klee_error(f):
        save_candidate = set()
        try:
            for _ in os.listdir(f):
                if ".err" in _ and ("external" not in _ or "exec" not in _):
                    #we are not interested in some klee errors
                    save_candidate.add(_.split(".")[0])
        except OSError:
            pass

        #remove useless ktests
        try:
            for _ in os.listdir(f):
                if _.split(".")[0] not in save_candidate:
                    os.unlink(os.path.join(f,_))
        except OSError:
		    pass
        if len(save_candidate) == 0:
            return False

        return True

    for _f in os.listdir(search_dir):
        #search dir should be the target dir
	if re.match(r'^klee-out-(\d+)', _f):
            if has_klee_error(search_dir+"/"+_f):
		try: 
                    shutil.move(search_dir+"/"+_f, subdir)
		except OSError:
		    pass
            else:
		try:
                    shutil.rmtree(search_dir+"/"+_f)
		except OSError:
		    pass
        elif "klee-last" == _f:
	    try: 
                os.remove(search_dir+"/"+"klee-last")
	    except OSError:
		pass

#mount a ramdisk in `dir_path` with `size` in bytes
def mount_ramdisk(dir_path, size):
    mkdir_force(dir_path)
    subprocess.Popen(['sudo', 'chmod', '777', dir_path]).wait()
    subprocess.Popen(['sudo', 'mount', '-t', 'tmpfs', '-o', 'size='+str(size), 'museram', dir_path ]).wait()

def unmount_ramdisk(dir_path):
    subprocess.Popen(['sudo', 'umount', dir_path ]).wait()
