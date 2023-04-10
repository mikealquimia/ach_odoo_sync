# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xmlrpc.client

class GetResPartner(models.Model):
    _name = 'odoo_sync'
    _description = 'Odoo Sync'
    
    name = fields.Char(string="Name", required=True)
    state = fields.Selection([('draft','Draft'),('logging','Logging'),('progress','Progress'),('done','Done')], string="State", default='draft')
    url_database = fields.Char(string="URL", required=True)
    database_name = fields.Char(string="Database", required=True)
    username_database = fields.Char(string="User Name", required=True)
    password_username_database = fields.Char(string="Password", required=True)
    
    odoo_sync_id = fields.Integer(string="Odoo Sync", compute="_compute_odoo_sync_id")
    ir_model_id = fields.Many2one('odoo_sync.ir_model', string="Model to import", domain="[('odoo_sync_id', '=', odoo_sync_id)]")
    ir_model_fields_ids = fields.One2many('odoo_sync.ir_model_fields', 'odoo_sync_id', string="Fields Import")

    type_sync = fields.Selection([('general','General'),('partner','Partner'),('sale','Sale'),('purchase','Purchase')], string="Type", default='general')

    #Get Res Partner
    type_import = fields.Selection([('all','All Contacts'),('sale','Specific based on sales date'),('create','Specific based on create date')], string="Type import")
    start_date = fields.Datetime(string="Start date")
    end_date = fields.Datetime(string="End date")
        
    def _compute_odoo_sync_id(self):
        for rec in self:
            if rec.id:
                rec.odoo_sync_id = rec.id
            else:
                rec.odoo_sync_id = 0
    
    def get_uid(self, url, db, username, password):
        url = self.url_database
        db = self.database_name
        username = self.username_database
        password = self.password_username_database
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
        version = common.version()
        uid = common.authenticate(db, username, password, {})
        return uid
            
    def logging_db(self):    
        url = self.url_database
        db = self.database_name
        username = self.username_database
        password = self.password_username_database
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
        version = common.version()
        uid = common.authenticate(db, username, password, {})
        if uid:
            self.write({'state':'logging'})
        else:
            raise UserError('An error has occurred with the connection data, verify your data access')
    
    def get_models(self):
        uid = self.get_uid(self.url_database,self.database_name,self.username_database,self.password_username_database) 
        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.url_database))
        if self.type_sync == 'general':
            ir_models = models.execute_kw(self.database_name, uid, self.password_username_database, 'ir.model', 'search_read', [[]], {'fields': ['name','model']})
        if self.type_sync == 'partner':
            ir_models = models.execute_kw(self.database_name, uid, self.password_username_database, 'ir.model', 'search_read', [[['model','=','res.partner']]], {'fields': ['name','model']})
        if ir_models:
            for model in ir_models:
                vals = {'name': model['name'],
                    'model': model['model'],
                    'odoo_sync_id': self.id}
                model_id = self.env['odoo_sync.ir_model'].create(vals)
            if self.type_sync == 'partner':
                self.write({'ir_model_id': model_id.id})
        else:
            raise UserError('The contacts module is not found in the external database')
    
    def get_fields(self):
        uid = self.get_uid(self.url_database,self.database_name,self.username_database,self.password_username_database) 
        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.url_database))
        ir_model_id = models.execute_kw(self.database_name, uid, self.password_username_database, 'ir.model', 'search', [[['model','=',self.ir_model_id.model]]], {'limit':1})
        ir_model_fields = models.execute_kw(self.database_name, uid, self.password_username_database, 'ir.model.fields', 'search_read', [[['model_id','=',ir_model_id]]], {'fields': ['name','field_description','ttype']})
        if ir_model_fields:
            for line_field in self.ir_model_fields_ids:
                line_field.unlink()
            for field in ir_model_fields:
                vals = {
                    'name': field['name'],
                    'name_import': field['name'],
                    'field_description_import': field['field_description'],
                    'ttype_import': field['ttype'],
                    'odoo_sync_id': self.id,
                }
                self.env['odoo_sync.ir_model_fields'].create(vals)
            ir_model_dest = self.env['ir.model'].search([('model','=',self.ir_model_id.model)],limit=1)
            fields_model = self.env['ir.model.fields'].search([('model_id','=',ir_model_dest.id)])
            for line in self.ir_model_fields_ids:
                for fields in fields_model:
                    if line.name_import == fields.name and line.ttype_import == fields.ttype:
                        line.write({'name_dest': fields.id})
    
    def import_data(self):
        uid = self.get_uid(self.url_database,self.database_name,self.username_database,self.password_username_database) 
        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.url_database))
        if self.type_import == 'sale':
            list_fields = []
            for field in self.ir_model_fields_ids:
                if field.import_field == True:
                    list_fields.append(field.name_import)
            try:
                sales = models.execute_kw(self.database_name, uid, self.password_username_database, 'sale.order', 'search_read', [[['confirmation_date','>=',self.start_date],['confirmation_date','<=',self.end_date]]],{'fields': ['partner_id']})
                partner_ids = []
                for sale in sales:
                    if sale['partner_id'][0] not in partner_ids:
                        partner_ids.append(sale['partner_id'][0])
                print('Sales:', len(sales),'Partners',len(partner_ids))
            except:
                print("can't read")
            for partner in partner_ids:
                try:
                    partner_vals = models.execute_kw(self.database_name, uid, self.password_username_database, 'res.partner', 'search_read', [[['id','=',partner],['parent_id','!=', False]]],{'fields': list_fields})
                    partner_vals[0]['ref'] = partner_vals[0].pop('id')
                    partner_vals[0]['comment'] = partner_vals[0].pop('parent_id')
                    if 'parent_id' in partner_vals[0]:
                        print(partner_vals)
                        #partner_vals[0]['comment'].remove([1])
                        self.env['res.partner'].create(partner_vals)
                except:
                    print('no read partner')
            #self.set_external_id()

    def set_external_id(self):
        partner_ids = self.env['res.partner'].search([('ref','!=',False)])
        for partner_id in partner_ids:
            sql1 = "SELECT * FROM res_partner WHERE id = %s;"
            params1 = (partner_id.ref,)
            self.env.cr.execute(sql1, params1)
            id_exits = self.env.cr.dictfetchall()
            if id_exits == False:
                print('set id')
                sql = "UPDATE res_partner SET id=%s, commercial_partner_id=%s WHERE id=%s;"
                params = (partner_id.ref,partner_id.ref,partner_id.id)
                self.env.cr.execute(sql, params)
        return
                
class OdooSyncIrModel(models.Model):
    _name = 'odoo_sync.ir_model'
    _description = 'Odoo Sync Ir Model'
    
    name = fields.Char(string="Name")
    model = fields.Char(string="Model")
    odoo_sync_id = fields.Many2one('odoo_sync', string="Odoo Sync")
    
class OdooSyncIrModelFields(models.Model):
    _name = 'odoo_sync.ir_model_fields'
    _description = 'Odoo Sync Ir Models Fields'
    
    name = fields.Char(string="Name")
    name_import = fields.Char(string="Field Import")
    field_description_import = fields.Char(string="Description Import")
    ttype_import = fields.Selection([
        ('binary','binary'),('boolean','boolean'),('char','char'),('date','date'),('datetime','datetime'),
        ('float','float'),('html','html'),('integer','integer'),('many2many','many2many'),('many2one','many2one'),('monetary','monetary'),
        ('many2one_reference','many2one_reference'),('one2many','one2many'),('reference','reference'),('selection','selection'),('text','text')],
        string="Type Import")
    name_dest = fields.Many2one('ir.model.fields', string="Field Dest")
    ttype_dest = fields.Selection([
        ('binary','Binary'),('boolean','Boolean'),('char','Char'),('date','Date'),('datetime','Datetime'),
        ('float','Float'),('html','Html'),('integer','Integer'),('many2many','Many2many'),('many2one','Many2one'),('monetary','Monetary'),
        ('many2one_reference','Many2one Reference'),('one2many','One2many'),('reference','Reference'),('selection','Selection'),('text','Text')],
        string="Type Dest", related="name_dest.ttype")
    import_field = fields.Boolean(string="Import", default=False)
    odoo_sync_id = fields.Many2one('odoo_sync', string="Odoo Sync")