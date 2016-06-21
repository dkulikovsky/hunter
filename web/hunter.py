#!/usr/bin/python
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from flup.server.fcgi import WSGIServer
import MySQLdb, re
import json
import socket
import difflib
import settings
import logging


app = Flask(__name__)
app.config.from_object(__name__)
url_prefix = "/hunter"
fh = logging.FileHandler('/var/log/hunter.log')
fh.setLevel(logging.DEBUG)
app.logger.addHandler(fh)

@app.before_request
def before_request():
    try:
        db = MySQLdb.connect(host='localhost',unix_socket='/var/run/mysqld/mysqld.sock',user=settings.user,passwd=settings.password,db=settings.db)
        db.autocommit(True)
    except MySQLdb.Error,e:
        app.logger.error("failed to connect to mysql: %d, %s" % (e.args[0],e.args[1]))
        abort(500)
    g.db = db.cursor()

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()

@app.route(url_prefix + '/')
def index():
    # get host index and list it
    try:
        g.db.execute("select distinct(h.hostname) from hosts h, hunter hu where hu.host_id = h.id order by h.hostname")
    except MySQLdb.Error,e:
        app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
        abort(500)

    hosts = []
    for h in g.db.fetchall():
        hosts.append(h[0])

    cli = 0

    try:
        cli = request.args.get('cli','')
    except keyerror:
        app.logger.debug('cli param is not set in request')

    if cli == "1" or cli == "on":
        if not hosts:
            return ''
        return "\n".join(hosts)
 
    return render_template("index.html", data = hosts)

@app.route(url_prefix + '/multi_diff', methods = ['GET',])
def multi_diff():
    # get host index and list it
    try:
        g.db.execute("select distinct(h.hostname) from hosts h, hunter hu where hu.host_id = h.id order by h.hostname")
    except MySQLdb.Error,e:
        app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
        abort(500)

    hosts = []
    for h in g.db.fetchall():
        hosts.append(h[0])

    if request.method == "GET":
            # hosts array may be defined in two different ways
            # using comma separated var hosts
            try:
                hosts_to_diff = request.args.get('hosts','')
                hosts_to_diff = re.sub(r',$','',hosts_to_diff)
            except KeyError:
                app.logger.debug('hosts array not defined')
            
            if hosts_to_diff:
                h_arr = hosts_to_diff.split(r',')
            else:
                h_arr = []
                for k in request.args.keys():
                    if re.match(r'host_\d+',k):
                        try:
                            var = request.args.get(k)
                            h_arr.append(var)
                        except KeyError:
                            app.logger.debug("expected var for %s, got KeyError" % ("host_"+k),)
                            break

            if len(h_arr):    
                for h in h_arr:
                    if not h in hosts:
                        app.logger.error("host %s not found in db %d" % (h,len(h_arr)))
                        return render_template("error.html",error = "host %s not found in db" % (h,))

                section = ""
                try:
                    section = request.args.get('section','')
                except KeyError:
                    app.logger.debug("section is absent in request")

                diff = get_hosts_diff(h_arr,section)
                
                return render_template("multi_diff.html", data = hosts, diff = diff, hosts = h_arr)

    return render_template("multi_diff.html", data = hosts, diff = "", hosts = [])

def get_hosts_diff(hosts,section):
    hosts_data = {}
    keys = {}

    sql = "SELECT h.key_name,h.val FROM hunter h, hosts hs WHERE h.host_id = hs.id"
    if section == 'std':
        sql += " and (h.key_name like 'hw%' or h.key_name like 'sys%')"
    elif section == 'hw':
        sql += " and h.key_name like 'hw%'"
    elif section == "sys":
        sql += " and h.key_name like 'sys%'"
    elif section == "dpkg":
        sql += " and h.key_name like 'dpkg%'"

    for host in hosts:
        try:
            g.db.execute(sql + " and hs.hostname = '%s' ORDER BY h.key_name" % (host,))
        except MySQLdb.Error,e:
            app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
            return render_template("error.html",error = "host %s not found in db" % (host,))

        if not hosts_data.has_key(host):
            hosts_data[host] = {}
        
        for key,val in g.db.fetchall():
            hosts_data[host][key] = val
            keys[key]=1
    
    output = []
    for key in keys:
        output_tmp = []
        output_tmp.append('<td>%s</td>' % (key,))
        first_val = ""
        for host in hosts:
            # if host has no key $key at all
            if not hosts_data[host].has_key(key):
                output_tmp.append('<td class="diff_abs"></td>')
                continue
            
            # we have first ocasion of key 
            if not first_val:
                output_tmp.append('<td>%s</td>' % (hosts_data[host][key],))
                first_val = hosts_data[host][key]
                continue
            
            if hosts_data[host][key] != first_val:
                output_tmp.append('<td class="diff_diff">%s</td>' % (hosts_data[host][key],))
                continue

            output_tmp.append('<td>%s</td>' % (hosts_data[host][key],))
        output.append(output_tmp)

    return output
    
@app.route(url_prefix + '/host', methods=['GET',])
def get_host():
    if request.method == 'GET':
        try:
            hostname = request.args.get('hostname','')
        except KeyError:
            app.logger.error("hostname is absent in request")
            abort(500)
        # filter out all bad chars from hostname param
        re.sub('\W+','',hostname)

        try:
            section = request.args.get('section','')
        except KeyError:
            app.logger.debug("section is absent in request")

        sql = "SELECT h.key_name,h.val FROM hunter h, hosts hs WHERE h.host_id = hs.id"
        if section == 'std':
            sql += " and (h.key_name like 'hw%' or h.key_name like 'sys%')"
        elif section == 'hw':
            sql += " and h.key_name like 'hw%'"
        elif section == "sys":
            sql += " and h.key_name like 'sys%'"
        elif section == "dpkg":
            sql += " and h.key_name like 'dpkg%'"

        try:
            g.db.execute(sql + " and hs.hostname = '%s' ORDER BY h.key_name" % (hostname,))
        except MySQLdb.Error,e:
            app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
            abort(500)

        # form output
        data = []
        for item in g.db.fetchall():
            data.append((item[0], item[1]))

        cli = 0
        try:
            cli = request.args.get('cli','')
        except KeyError:
            app.logger.debug('cli param is not set in request')

        
        if cli == "1" or cli == "on":
            output = "hostname="+hostname
            for item in data:
                output += "\n%s=%s"%(item[0],item[1])
            return output

        return render_template("host.html",data = data, host = hostname)
            
@app.route(url_prefix + '/host_option', methods = ['GET',])
def host_option():
    if request.method == 'GET':
        try:
            hostname = request.args.get('hostname','')
            option = request.args.get('option','')
        except KeyError:
            app.logger.error("hostname is absent in request")
            abort(500)
        # filter out all bad chars from hostname param
        re.sub('\W+','',hostname)

        cli = 0
        try:
            cli = request.args.get('cli','')
        except KeyError:
            app.logger.debug('cli param is not set in request')

        try:
            g.db.execute("SELECT h.key_name,h.val FROM hunter h, hosts hs WHERE h.host_id = hs.id and hs.hostname = '%s' and h.key_name = '%s'" % (hostname,option))
        except MySQLdb.Error,e:
            app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
            abort(500)

        # form output
        data = []
        for item in g.db.fetchall():
            data.append((item[0], item[1]))


        if cli == "1" or cli == "on":
            if not data:
                return ''
            return str(data[0][1])
        else:
            if not data:
                return render_template("host.html",data=() , host = hostname)
            return render_template("host.html",data = data, host = hostname)
            

@app.route(url_prefix + '/diff', methods = ['GET',])
def host_diff():
    if request.method == 'GET':
        try:
            host1 = request.args.get('host1','')
            host2 = request.args.get('host2','')
        except KeyError:
            app.logger.error("host1 or host2 is absent in request")
            abort(500)

        cli = 0
        try:
            cli = request.args.get('cli','')
        except KeyError:
            app.logger.debug('cli param is not set in request')

        # filter out all bad chars from hostname param
        re.sub('\W+','',host1)
        re.sub('\W+','',host2)

        try:
            section = request.args.get('section','')
        except KeyError:
            app.logger.debug("section is absent in request")

        sql = "SELECT h.key_name,h.val FROM hunter h, hosts hs WHERE h.host_id = hs.id"
        if section == 'std':
            sql += " and (h.key_name like 'hw%' or h.key_name like 'sys%')"
        elif section == 'hw':
            sql += " and h.key_name like 'hw%'"
        elif section == "sys":
            sql += " and h.key_name like 'sys%'"
        elif section == "dpkg":
            sql += " and h.key_name like 'dpkg%'"


        data = {}
        try:
            # get host1 config
            g.db.execute(sql + " and hs.hostname = '%s'" % (host1,))
            data['host1'] = []
            for item in g.db.fetchall():
                data['host1'].append('%s=%s' % (item[0],item[1]))
            
             # get host2 config
            g.db.execute(sql + " and hs.hostname = '%s'" % (host2,))
            data['host2'] = []
            for item in g.db.fetchall():
                data['host2'].append('%s=%s' % (item[0],item[1]))
        except MySQLdb.Error,e:
            app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
            abort(500)

        # get all hosts
        try:
            g.db.execute("SELECT DISTINCT(h.hostname) FROM hosts h, hunter hu WHERE hu.host_id = h.id ORDER BY h.hostname")
        except MySQLdb.Error,e:
            app.logger.error("failed to execute query in mysql: %d, %s" % (e.args[0],e.args[1]))
            abort(500)
    
        allhosts = []
        for h in g.db.fetchall():
            allhosts.append(h[0])

        # form diff
        if cli == "1" or cli == "on":
            diff = difflib.unified_diff(data['host1'],data['host2'],fromfile=host1,tofile=host2)
            return '\n'.join(diff)+"\n"
        else:
            diff = difflib.HtmlDiff().make_table(data['host1'],data['host2'])
            diff = re.sub(r'<tr>(.*?diff_chg.*?)</tr>',r'<tr class="diff_str">\1</tr>',diff)
            diff = re.sub(r'<tr>(.*?diff_sub.*?)</tr>',r'<tr class="diff_str">\1</tr>',diff)
            return render_template("diff.html",data = diff, hosts = (host1, host2), allhosts = allhosts)
    else:
        return render_template("diff.html",data = '',hosts = ('',''))

@app.route(url_prefix + '/upload', methods=['POST','GET'])
def hunter_acceptor():
    if request.method == 'POST':
        # parse data
        try:
            data = request.form['data']
        except KeyError:
            app.logger.error("failed to get data from request")
            abort(500)

        try: 
            data = json.loads(data)
        except:
            app.logger.error("failed to parse data in json")
            abort(500)

        upload_data(data)


    return "OK"

def upload_data(data):
    if data.has_key('output') and data.has_key('hostname'):
        for item in data['output']:
            if re.search(r'\S+', data['hostname']):
                host_id = get_host_id(data['hostname'])
                insert_or_update(host_id,item[0],item[1])
            else:
                app.logger.error("hostname is empty")
                abort(500)
    else:
        app.logger.error("input has no data")
        abort(500)

def insert_or_update(hid,key,val):
    try:
        g.db.execute("SELECT id FROM hunter WHERE host_id = %d and key_name = '%s'" % (hid,key))

        item_id = g.db.fetchone()
        if item_id:
            g.db.execute("UPDATE hunter SET val = '%s' WHERE id = %d" % (val,item_id[0]))
        else:
            g.db.execute("INSERT INTO hunter (host_id,key_name ,val) VALUES (%d,'%s','%s')" % (hid,key,val))
    except MySQLdb.Error,e:
        app.logger.error("failed to execute query to mysql: %d, %s" % (e.args[0],e.args[1]))
        abort(500)
    
def get_host_id(hostname):
    try:
        g.db.execute("SELECT id FROM hosts WHERE hostname = '%s'" % (hostname,))
        host_id = g.db.fetchone()
        if host_id:
            return host_id[0]
        else:
            return create_new_host(hostname)
    except MySQLdb.Error,e:
        app.logger.error("failed to execute query to mysql: %d, %s" % (e.args[0],e.args[1]))
        abort(500)
    
def create_new_host(hostname):
    try:
        g.db.execute("INSERT INTO hosts (hostname) values ('%s')" % (hostname,))
        # get new id from mysql
        g.db.execute("SELECT id FROM hosts WHERE hostname = '%s'" % (hostname,))
        host_id = g.db.fetchone()
        if host_id:
            return host_id[0]
        else:
            app.logger.error("failed to create new host %s for sone unknown reason" % (hostname,))
            abort(500)
    except:
        app.logger.error("failed to create new host in db")
        abort(500)

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
