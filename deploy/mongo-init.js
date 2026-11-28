// This script runs only when the isolated MongoDB volume is first created.
// Every password is generated outside Git and supplied through the container environment.
const env = process.env;
const authDb = db.getSiblingDB('auth_db');
authDb.createUser({user: 'auth_app', pwd: env.AUTH_APP_PASSWORD, roles: [{role: 'readWrite', db: 'auth_db'}]});

const registry = db.getSiblingDB('registry_db');
registry.createRole({role: 'registry_claim', privileges: [{resource: {db: 'registry_db', collection: 'student_registry'}, actions: ['find', 'update']}], roles: []});
registry.createUser({user: 'registry_app', pwd: env.REGISTRY_APP_PASSWORD, roles: ['registry_claim']});
registry.createUser({user: 'registry_importer', pwd: env.REGISTRY_IMPORTER_PASSWORD, roles: [{role: 'readWrite', db: 'registry_db'}]});
registry.student_registry.createIndex({student_id: 1}, {unique: true, name: 'registry_student_id_unique'});
registry.student_registry.createIndex({university_email: 1}, {unique: true, name: 'registry_email_unique'});

const cases = db.getSiblingDB('cases_db');
cases.createUser({user: 'cases_app', pwd: env.CASES_APP_PASSWORD, roles: [{role: 'readWrite', db: 'cases_db'}]});
cases.createRole({role: 'case_stats_read', privileges: [{resource: {db: 'cases_db', collection: 'cases'}, actions: ['find']}], roles: []});
cases.createUser({user: 'stats_reader', pwd: env.STATS_READER_PASSWORD, roles: ['case_stats_read']});

const audit = db.getSiblingDB('audit_db');
audit.createRole({role: 'audit_append_only', privileges: [{resource: {db: 'audit_db', collection: 'events'}, actions: ['insert', 'createIndex']}], roles: []});
audit.createRole({role: 'audit_find_only', privileges: [{resource: {db: 'audit_db', collection: 'events'}, actions: ['find']}], roles: []});
audit.createUser({user: 'audit_app', pwd: env.AUDIT_APP_PASSWORD, roles: ['audit_append_only']});
audit.createUser({user: 'audit_reader', pwd: env.AUDIT_READER_PASSWORD, roles: ['audit_find_only']});
audit.events.createIndex({timestamp: -1, _id: -1}, {name: 'audit_timeline'});
