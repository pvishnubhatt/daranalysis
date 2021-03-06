
from models import Entry
from models import User
from models import Project
from models import Vendor
from models import Objective
from models import EvaluationCriteria
from models import DEFAULT_PROJECT_NAME
from models import project_db_key
from functools import wraps
import json
import time
import datetime
from flask import request, session, Response, url_for, redirect
from google.appengine.api import mail
from google.appengine.api import app_identity
import math
import urllib2

firebase_server_key = "key=AIzaSyDxwE1m7WjI6400WD9GadNJqoZfJvBmjGs"
fcm_server = "https://fcm.googleapis.com/fcm/send"
fcm_headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'Authorization' : firebase_server_key}
sender_address = "DAR Admin <jaisairam0170@gmail.com>   "
total_max_limit = 1000
gae_environments = {'daranalysis-200000' : 'blue',
                'daranalysis-160000' : 'red',
                'daranalysis-201000' : 'amber',
                'daranalysis-202000' : 'yellow',
                'daranalysis-203000' : 'green'}
super_user_name = "Superuser"
CREATE_MODE = "__CREATE__"
ENTRY_SAVED_TITLE = "DAR Entry Saved"
ENTRY_SAVED_MESSAGE = "Hello {toUser}, {aboutUser} has just saved DAR entry"
DAR_TITLE = 'This is my {string} formatted with {args} arguments'
PROJECT_REMINDER_TITLE = "DAR Project Reminder ({env}) : Your DAR needs to completed"
PROJECT_REMINDER_MESSAGE = "As an admin your DAR {projectId} in {env} environment, \
                                it needs to be attended to, please remind users using Manage button"

def get_project_db_name(rname=DEFAULT_PROJECT_NAME):
    return rname

#Gets evaluation_criteria from db - this needs to implement evaluation_criteria-lifecycle - right now it is a singleton
def get_projects_from_db(userId):
    if userId:
        project_query = Project.query(Project.userIds.IN([userId]))
    else:
        project_query = Project.query()
    return project_query.fetch(total_max_limit)

#Gets evaluation_criteria from db - this needs to implement evaluation_criteria-lifecycle - right now it is a singleton
def get_project_from_db(projectId):
    project_query = Project.query(Project.projectId == projectId)
    if project_query.count() < 1:
        return None
    else:
        return project_query.fetch(1)[-1]

def get_entry_from_db(projectId, userId):
    entrys_query = Entry.query(Entry.user.identity == userId, Entry.project.projectId == projectId)
    if entrys_query.count() < 1:
        return None
    else:
        return entrys_query.fetch(1)[-1]

def get_entrys_from_given_project_db(projectId):
    entrys_query = Entry.query(Entry.project.projectId == projectId)
    return entrys_query.fetch(total_max_limit)

def get_entrys_from_given_user_db(projectId, userId):
    entrys_query = Entry.query(Entry.user.identity == userId, Entry.project.projectId == projectId)
    return entrys_query.fetch(total_max_limit)

def get_users_from_db(projectId=None):
    if projectId and projectId != "":
        project = get_project_from_db(projectId)
        if project is not None:
            userIds = project.userIds
            users = []
            for userId in userIds:
                user = get_user_from_db(userId)
                users.append(user)
            return users
    else:
        users_q = User.query(User.type != super_user_name)
        users = users_q.fetch(total_max_limit)
        return users

    return None

def get_user_from_db(userId):
    if "@" in userId:
        users_q = User.query(User.email == userId)
    else:
        users_q = User.query(User.identity == userId)
    if users_q.count() < 1:
        return None
    else:
        return users_q.fetch(1)[-1]

def update_users_project(projectId, userIds):
    project = get_project_from_db(projectId)
    project.userIds = userIds
    project.put()
    return project

def update_user(userId, email, type, password, projectIds):
    user = get_user_from_db(userId)
    if user is None:
        project_name = get_project_db_name()
        user = User(parent=project_db_key(project_name))
        user.identity = userId
        user.projectIds = []
    user.email = email
    user.type = type
    user.password = password
    if projectIds:
        for projId in projectIds:
            if projId and projId != CREATE_MODE and projId not in user.projectIds:
                    user.projectIds.append(projId)
                    project = get_project_from_db(projId)
                    if project:
                        project.userIds.append(userId)
                        project.put()

    user.put()
    time.sleep(1)

    #repeat to create empty entrys by default
    if projectIds:
        for projId in projectIds:
            project = get_project_from_db(projId)
            if project:
                entry = get_entry_from_db(projId, userId)
                if entry is None:
                    update_entry(projId, userId, None, None, None, None)

    return user

def getArrayOfDict(bos):
    # this is not good
    bot = bos[0]
    # this is even worse
    bot = '[' + bot + ']'
    bol = json.loads(bot)
    return bol

def update_project(projectId, department, group, description, defaultPassword, userIds, vendorIds, due_date, bos):
    project_name = get_project_db_name()
    project = get_project_from_db(projectId)
    if project is None:
        project = Project(parent=project_db_key(project_name))
        project.projectId = projectId
        project.objectiveIds = []
    project.department = department
    project.description = description
    project.group = group
    project.defaultPassword = defaultPassword
    project.userIds = userIds
    project.vendorIds = vendorIds
    for ui in userIds:
        user = get_user_from_db(ui)
        if user and projectId not in user.projectIds:
            user.projectIds.append(projectId)
            user.put()
    for vi in vendorIds:
        vendor = get_user_from_db(vi)
        if vendor and projectId not in vendor.projectIds:
            vendor.projectIds.append(projectId)
            vendor.put()
    if due_date is None or due_date == "":
        project.due_date = datetime.datetime.now()
    else:
        project.due_date = datetime.datetime.strptime(due_date.split(" ")[0], "%Y-%m-%d")

    bol = getArrayOfDict(bos)
    if len(project.objectiveIds) > 0:
        nnbos = []
        for bo in bol:
            nnbos.append(bo["objectiveId"])
            nnecs = []
            if "evaluation_criteria" in bo:
                for ec in bo["evaluation_criteria"]:
                    nnecs.append(ec["evaluation_criterionId"])
                rbo = get_objective_from_db(projectId, bo["objectiveId"])
                if rbo:
                    for pec in rbo.evaluation_criteriaIds:
                        if pec not in nnecs:
                            print "deleting " + pec
                            delete_evaluation_criterion_from_db(projectId, rbo.objectiveId, pec)

        for pbo in project.objectiveIds:
            if pbo not in nnbos:
                print "deleting " + pbo
                project.objectiveIds.remove(pbo)
                delete_objective_from_db(projectId, pbo)
    # get basic in
    project.put()
    #get more stuff
    for bo in bol:
        #print bo["objectiveId"] + ", " + bo["description"] + ", " + bo["weight"]
        boid = bo["objectiveId"]
        nbo = get_objective_from_db(projectId, boid)
        if nbo is None:
            nbo = Objective(parent=project_db_key(project_name))
            nbo.objectiveId = boid
            nbo.projectId = projectId
            nbo.evaluation_criteriaIds = []
        nbo.description = bo["description"]
        nbo.weight = int(bo["weight"])
        if "evaluation_criteria" in bo:
            for ec in bo["evaluation_criteria"]:
                ecid = ec["evaluation_criterionId"]
                nec = get_evaluation_criteria_from_db(projectId, boid, ecid)
                #print "\t" + projectId + ", " + ec["evaluation_criterionId"] + ", " + ec["evaluation_criterion"] + "\n\t" + str(nec)
                if nec is None:
                    nec = EvaluationCriteria(parent=project_db_key(project_name))
                    nec.evaluation_criterionId = ecid
                    nec.objectiveId = boid
                    nec.projectId = projectId
                nec.evaluation_criterion = ec["evaluation_criterion"]
                nec.put()
                if ecid in nbo.evaluation_criteriaIds:
                    iiidx = nbo.evaluation_criteriaIds.index(ecid)
                    nbo.evaluation_criteriaIds[iiidx] = ecid
                else:
                    nbo.evaluation_criteriaIds.append(ecid)
        nbo.put()
        if nbo.objectiveId in project.objectiveIds:
            iidx = project.objectiveIds.index(nbo.objectiveId)
            project.objectiveIds[iidx] = nbo.objectiveId
        else:
            project.objectiveIds.append(nbo.objectiveId)

    project.put()
    return project

def get_objective_from_db(projectId, objectiveId):
    objectives_query = Objective.query(Objective.objectiveId == objectiveId,
                                       Objective.projectId == projectId)
    if objectives_query.count() < 1:
        return None
    else:
        return objectives_query.fetch(1)[-1]

def get_evaluation_criteria_from_db(projectId, objectiveId, evaluation_criterionId):
    evaluation_criteria_query = EvaluationCriteria.query(EvaluationCriteria.evaluation_criterionId == evaluation_criterionId,
                                                         EvaluationCriteria.objectiveId == objectiveId,
                                                         EvaluationCriteria.projectId == projectId)
    if evaluation_criteria_query.count() < 1:
        return None
    else:
        return evaluation_criteria_query.fetch(1)[-1]

def get_entry_status(projectId, userId):
    project = get_project_from_db(projectId)
    entry = get_entry_from_db(projectId, userId)
    lenv = len(project.vendorIds)
    lene = 0
    for objectiveId in project.objectiveIds:
        objective = get_objective_from_db(projectId, objectiveId)
        if objective:
            evaluation_criteriaIds = objective.evaluation_criteriaIds
            if evaluation_criteriaIds:
                lene += len(evaluation_criteriaIds)
    tlenv = lene * lenv
    if entry and entry.vendor_output:
        vsplits = json.loads(entry.vendor_output)
        elenv = len(vsplits.keys())
    if  entry is None:
        return "Incomplete"
    else:
        if (entry and entry.evaluation_criteria_output is None) or \
            (entry and entry.evaluation_criteria_output and len(entry.evaluation_criteria_output) == 0) or \
            (entry and entry.evaluation_criteria_output and len(entry.evaluation_criteria_output) < lene) or \
            (entry and entry.vendor_output is None) or \
            (entry and entry.vendor_output and elenv == 0) or \
            (entry and entry.vendor_output and elenv < tlenv):
            cur_date = datetime.datetime.now()
            if project.due_date < cur_date:
                return "Late"
            else:
                return "Incomplete"
        else:
            return "OK"


def get_project_status(projectId):
    entrys = get_entrys_from_given_project_db(projectId)
    status = "OK"
    total = len(entrys)
    if total > 0:
        current = 0
        for entry in entrys:
            status = get_entry_status(projectId, entry.user.identity)
            if status == "OK":
                current += 1
        percentage = float (current * 100 / total)
    else:
        percentage = 0
        status = "Incomplete"
    return status, percentage

def delete_evaluation_criterion_from_db(projectId, objectiveId, ecid):
    eval_criterion = get_evaluation_criteria_from_db(projectId, objectiveId, ecid)
    objective = get_objective_from_db(projectId, objectiveId)
    objective.evaluation_criteriaIds.remove(ecid)
    objective.put()
    if eval_criterion:
        key = eval_criterion.key
        if key:
            print '\tdeleting ' + eval_criterion.evaluation_criterionId
            key.delete()

def delete_objective_from_db(projectId, objectiveId):
    objective = get_objective_from_db(projectId, objectiveId)
    if objective:
        for ecid in objective.evaluation_criteriaIds:
            # print objective
            # print " *** looking for : " + objectiveId + ", " + ecid
            evaluation_criterion = get_evaluation_criteria_from_db(projectId, objectiveId, ecid)
            if evaluation_criterion:
                key = evaluation_criterion.key
                if key:
                    print '\tdeleting ' + evaluation_criterion.evaluation_criterion
                    key.delete()
        key = objective.key
        if key:
            print '\tdeleting ' + objective.objectiveId
            key.delete()


def delete_project_from_db(projectId):
    print 'deleting ' + projectId
    project = get_project_from_db(projectId)
    entrys = get_entrys_from_given_project_db(projectId)
    vendorIds = project.vendorIds
    for vendorId in vendorIds:
        vendor = get_vendor_from_db(vendorId)
        if vendor:
            if projectId in vendor.projectIds:
                vendor.projectIds.remove(projectId)
                vendor.put()
    userIds = project.userIds
    for userId in userIds:
        user = get_vendor_from_db(userId)
        if user:
            if projectId in user.projectIds:
                user.projectIds.remove(projectId)
                user.put()
    for objectiveId in project.objectiveIds:
        delete_objective_from_db(projectId, objectiveId)
    for entry in entrys:
        key = entry.key
        if key:
            key.delete()
    key = project.key
    if key:
        key.delete()

def delete_entry_from_db(entry):
    key = entry.key
    if key:
        key.delete()

def delete_users_from_db():
    users = get_users_from_db(None)
    if users:
        for user in users:
            delete_user_from_db(user.identity)

def delete_user_from_db(userId):
    user = get_user_from_db(userId)
    if user:
        projectIds = user.projectIds
        for projectId in projectIds:
            entrys = get_entry_from_db(projectId, userId)
            for entry in entrys:
                delete_entry_from_db(entry)
        key = user.key
        if key:
            key.delete()

def update_entry(projectId, userId, evaluation_criteria, evaluation_criteria_output, vendor_output, weights):
    entry = get_entry_from_db(projectId, userId)
    if entry is None:
        project_name =  DEFAULT_PROJECT_NAME
        entry = Entry(parent=project_db_key(project_name))
        entry.user = get_user_from_db(userId)
        entry.project = get_project_from_db(projectId)
    if evaluation_criteria:
        entry.evaluation_criteria = evaluation_criteria.split(",")
    if evaluation_criteria_output:
        entry.evaluation_criteria_output = evaluation_criteria_output.split(",")
    if weights:
        sweights = json.loads(weights)
        for weight in sweights:
            entry.weights.append(weight + ":" + str(sweights[weight]))
    if vendor_output:
        entry.vendor_output = vendor_output
    entry.put()
    return entry

def get_vendors_from_db(projectId=None):
    if projectId and projectId != "":
        project = get_project_from_db(projectId)
        if project is not None:
            vendorIds = project.vendorIds
            vendors = []
            for vendorId in vendorIds:
                vendor = get_vendor_from_db(vendorId)
                vendors.append(vendor)
            return vendors
    else:
        vendors_q = Vendor.query()
        vendors = vendors_q.fetch(total_max_limit)
        return vendors

    return None

def get_vendor_from_db(vendorId):
    vendors_q = Vendor.query(Vendor.identity == vendorId)
    if vendors_q.count() < 1:
        return None
    else:
        return vendors_q.fetch(1)[-1]

def update_vendor(vendorId, email, projectIds):
    vendor = get_vendor_from_db(vendorId)
    if vendor is None:
        project_name = get_project_db_name()
        vendor = Vendor(parent=project_db_key(project_name))
        vendor.identity = vendorId
        vendor.projectIds = []
    vendor.email = email
    if projectIds:
        for projId in projectIds:
            if projId and projId != CREATE_MODE and projId not in vendor.projectIds:
                    vendor.projectIds.append(projId)
                    project = get_project_from_db(projId)
                    if project:
                        project.vendorIds.append(vendorId)
                        project.put()
    vendor.put()
    time.sleep(1)
    return vendor


def delete_vendor_from_db(vendorId):
    vendor = get_vendor_from_db(vendorId)
    if vendor:
        key = vendor.key
        if key:
            key.delete()

def delete_vendors_from_db():
    vendors = get_vendors_from_db(None)
    if vendors:
        for vendor in vendors:
            key = vendor.key
            if key:
                key.delete()

def get_all_data_from_calc(project):
    entrys = get_entrys_from_given_project_db(project.projectId)
    criteria_average_dict = {}
    vendor_scores_dict =  {}
    criteria_to_users_map = {}
    total = len(entrys)
    if total > 0:
        for entry in entrys:
            for weight_splits in entry.weights:
                req_weight = weight_splits.split(":")
                try:
                    f_weight = float(req_weight[1])
                except ValueError:
                    f_weight = 0.0
                if req_weight[0] in criteria_average_dict:
                    criteria_average_dict[req_weight[0]] += f_weight
                else:
                    criteria_average_dict[req_weight[0]] = f_weight
                rkey = req_weight[0].replace(" ", "^")
                if rkey not in criteria_to_users_map:
                    criteria_to_users_map[rkey] = []
                criteria_to_users_map[rkey].append({"userId": str(entry.user.identity), "weight": str(req_weight[1])})

            if entry.vendor_output:
                vsplits = json.loads(entry.vendor_output)
                for key in vsplits:
                    score = int(vsplits[key])
                    nkey = str(key)
                    if key in vendor_scores_dict:
                        vendor_scores_dict[nkey] += int(score)
                    else:
                        vendor_scores_dict[nkey] = int(score)

        for key in criteria_average_dict:
            criteria_average_dict[key] = float(criteria_average_dict[key]) / float(total)

        for key in vendor_scores_dict:
            vendor_scores_dict[key] = float(vendor_scores_dict[key]) / float(total)

    return criteria_average_dict, vendor_scores_dict, criteria_to_users_map

def get_business_objectives_from_db(projectId, withCalc):
    bos_db = []
    topVendor = None
    project = get_project_from_db(projectId)
    start = time.clock()
    criteria_to_users_map = None
    if withCalc:
        start = time.clock()
        criteria_average_dict, vendor_scores_dict, criteria_to_users_map = get_all_data_from_calc(project)
    print str(time.clock() - start)
    start = time.clock()
    for objectiveId in project.objectiveIds:
        objective = get_objective_from_db(projectId, objectiveId)
        if objective:
            evaluation_criteriaIds = objective.evaluation_criteriaIds
            evaluation_criteria = []
            for evaluation_criterionId in evaluation_criteriaIds:
                evaluation_criterion = get_evaluation_criteria_from_db(projectId, objectiveId, evaluation_criterionId)
                if evaluation_criterion:
                    if withCalc:
                        calculations = {}
                        if evaluation_criterion.evaluation_criterion in criteria_average_dict:
                            criteria_average = criteria_average_dict[evaluation_criterion.evaluation_criterion]
                            calculations["criteria_average"] = criteria_average
                        else:
                            calculations["criteria_average"] = 0
                            calculations["criteria_weight"] = 0
                        for vendorId in project.vendorIds:
                            key = str(vendorId) + "_vendor_score"
                            skey = str(vendorId).replace(" ", "^")+"^"+evaluation_criterion.evaluation_criterion.replace(" ", "^")
                            if skey in vendor_scores_dict:
                                vendor_score = float(vendor_scores_dict[skey])
                            else:
                                vendor_score = 0
                            calculations[key] = vendor_score
                        evaluation_criterion.calculations = calculations
                    evaluation_criteria.append(evaluation_criterion)
            objective.evaluation_criteria = evaluation_criteria
            bos_db.append(objective)

    print str(time.clock() - start)
    return bos_db, criteria_to_users_map

def send_reminders(tolist, title, content):
    for toaddr in tolist:
        user = get_user_from_db(toaddr)
        send_message(user, title, content)

def send_entry_completion(projectId, userId):
    user = get_admin_user(projectId)
    if user:
        title = ENTRY_SAVED_TITLE
        content = ENTRY_SAVED_MESSAGE.format(toUser=user.identity, aboutUser=userId)
        send_message(user, title, content)

def get_admin_user(projectId):
    users = get_users_from_db(projectId)
    for user in users:
        if user.type != "User":
            return user
    return None

def run_manage():
    gae_app_id = app_identity.get_application_id()
    gae_env = None
    if gae_app_id in gae_environments:
        gae_env = gae_environments[gae_app_id]
        print "Running in " + gae_env + " : " + gae_app_id
    else:
        print 'Running in ' + gae_app_id
    if gae_app_id is None and gae_env is None:
        gae_env = "purple"
    project_query = Project.query()
    projects = project_query.fetch(total_max_limit)
    if projects:
        print "Managing " + str(len(projects))
    count = 0
    for project in projects:
        print project.projectId
        count += 1
        if count > 5    :
            time.sleep(2)
        status, percentage = get_project_status(project.projectId)
        print "\t" + str(status) + ", " + str(percentage)
        if status != "OK" or percentage < 100:
            user = get_admin_user(project.projectId)
            print "\tAdmin to " + project.projectId + " is " + user.identity
            if user:
                title = PROJECT_REMINDER_TITLE.format(env=gae_env)
                message = PROJECT_REMINDER_MESSAGE.format(projectId=project.projectId, env=gae_env)
                send_message(user, title, message)
                time.sleep(2)

def send_message(user, title, message):
    print "Sending email to " + user.email
    mail.send_mail(sender=sender_address,
                   to=user.email,
                   subject=title,
                   body=message)
    if hasattr(user, 'token') and user.token:
        send_notification(user.token, title, message)

def send_notification(toaddr, title, content):
    print 'send_notification ' + toaddr + ", " + title + ", " + content
    headers = fcm_headers
    url = fcm_server
    data = {'priority': 'high', 'to': toaddr, \
            'notification' : {'badge': '1', 'sound' : 'default', 'title' : title, 'body' : content}}
    try:
        opener = urllib2.build_opener()
        req = urllib2.Request(url, data=json.dumps(data), headers=headers)
        resp = opener.open(req)
        print "OK - Notification sent"
    except urllib2.HTTPError as e:
        error_message = e.read()
        print error_message

def update_token(userId, token):
    print "In update_token: " + userId + ", " + token
    user = get_user_from_db(userId)
    if user.token != token:
        user.token = token
        user.put()

def get_user_type_from_db(identity):
    user = get_user_from_db(identity)
    return user.type

def is_user_first_login(identity):
    user = get_user_from_db(identity)
    return user.isFirstLogin


