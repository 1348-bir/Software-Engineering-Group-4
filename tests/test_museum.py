import base64
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import app
from museum.catalog import active, rule_for


class MuseumIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = patch.dict(app.config, MUSEUM_ADMIN_PASSWORD='test-museum-password',
                                 MUSEUM_DATA_DIR=self.tmp.name)
        self.config.start()
        self.extensions = patch.dict(app.extensions)
        self.extensions.start()
        app.extensions.pop('museum_catalog', None)
        self.client = app.test_client()
        self.auth = {'Authorization':'Basic '+base64.b64encode(b'admin:test-museum-password').decode(),
                     'X-Museum-Request':'1'}

    def tearDown(self):
        self.extensions.stop()
        self.config.stop()
        self.tmp.cleanup()

    def post(self, kind, value):
        response = self.client.post('/museum/api/admin/'+kind, json=value, headers=self.auth)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def upload(self, name, content):
        response = self.client.post('/museum/api/admin/upload', query_string={'name':name},
                                    data=content, headers=self.auth)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.json

    def test_home_project_and_public_player(self):
        for url in ('/', '/projects'):
            self.assertIn('href="/museum/"', self.client.get(url).get_data(as_text=True))
        for path in ('/', '/terminal', '/app.js', '/admin.js', '/style.css', '/control.css', '/terminal.js'):
            with self.client.get('/museum'+path) as response:
                self.assertEqual(response.status_code, 200)

    def test_admin_auth_and_write_header(self):
        self.assertEqual(self.client.get('/museum/admin').status_code, 401)
        with self.client.get('/museum/admin', headers=self.auth) as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/museum/api/admin/catalog').status_code, 401)
        self.assertEqual(self.client.post('/museum/api/admin/terminals', json={},
                         headers={'Authorization':self.auth['Authorization']}).status_code, 403)
        with patch.dict(app.config, MUSEUM_ADMIN_PASSWORD=''):
            self.assertEqual(self.client.get('/museum/admin').status_code, 503)

    def test_media_upload_range_and_catalog_persistence(self):
        asset = self.upload('label.txt', '展品说明'.encode())
        updated = self.post('assets', {**asset, 'name':'展品', 'category':'展厅',
                                       'subtitle':'文字说明','watermark':'第四组'})
        self.assertEqual(updated['category'], '展厅')
        path = '/museum/media/'+asset['id']
        with self.client.get(path, headers={'Range':'bytes=0-2'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, '展'.encode())
        self.assertEqual(self.client.get('/museum/catalog.json').status_code, 404)
        self.assertEqual(self.client.post('/museum/api/admin/upload?name=unsafe.html',
                         data=b'<html>', headers=self.auth).status_code, 400)
        app.extensions.pop('museum_catalog')
        catalog = self.client.get('/museum/api/admin/catalog', headers=self.auth).json
        self.assertEqual(catalog['assets'][asset['id']]['watermark'],'第四组')
        self.assertTrue((Path(self.tmp.name)/'catalog.json').is_file())

    def test_targeting_layout_and_future_schedule(self):
        a = self.upload('east.txt', b'East')
        b = self.upload('west.txt', b'West')
        for key, group in (('east1','East'),('east2','East'),('west1','West')):
            self.post('terminals',{'id':key,'name':key,'group':group})
        standard = {'enabled':True,'priority':0}
        east = self.post('plans',dict(standard,name='East split',target='group:East',
                                      layout='split',regions=[[a['id']],[b['id']]]))
        west = self.post('plans',dict(standard,name='West',target='terminal:west1',
                                      layout='single',regions=[[b['id']]]))
        self.post('tickers',dict(standard,name='East notice',target='group:East',text='East',speed=15))
        self.post('tickers',dict(standard,name='One screen',target='terminal:east1',text='One',speed=15))
        self.post('tickers',dict(standard,name='Future',target='*',text='Future',speed=15,
                                rule={'repeat':'once','from':'2099-01-01','until':'2099-01-01',
                                      'start':'09:00','end':'10:00'}))
        f1,f2,f3=(self.client.get('/museum/api/feed?id='+k).json for k in ('east1','east2','west1'))
        self.assertEqual((f1['plan'],f2['plan'],f3['plan']),(east['id'],east['id'],west['id']))
        self.assertEqual(f1['regions'],f2['regions'])
        self.assertEqual(f1['regions'][0][0]['url'],'/museum/media/'+a['id'])
        self.assertEqual([v['text'] for v in f1['tickers']],['One','East'])
        self.assertEqual([v['text'] for v in f2['tickers']],['East'])
        self.assertEqual(f3['tickers'],[])
        self.assertEqual(self.client.delete('/museum/api/admin/assets',json={'id':a['id']},
                         headers=self.auth).status_code,400)

    def test_document_import_preview_pages_and_removal(self):
        def render_fixture(source, pages):
            self.assertEqual(source.suffix, '.pptx')
            pages.mkdir()
            for page in (1, 2):
                (pages / f'{page}.png').write_bytes(b'converted PNG '+bytes([page]))
            return 2

        with patch('museum.render', side_effect=render_fixture):
            document = self.upload('gallery.pptx', b'example presentation')
        self.assertEqual(document['page_count'], 2)
        key = document['id']
        preview = self.client.get('/museum/api/document/'+key).json
        self.assertEqual(preview['regions'][0][0]['page_count'], 2)
        with self.client.get(f'/museum/media/{key}/page/2') as response:
            self.assertEqual(response.mimetype, 'image/png')
            self.assertEqual(response.data, b'converted PNG \x02')
        self.assertEqual(self.client.get(f'/museum/media/{key}/page/3').status_code, 404)
        self.assertEqual(self.client.get(f'/museum/media/{key}').status_code, 401)
        with self.client.get(f'/museum/media/{key}', headers=self.auth) as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(self.client.delete('/museum/api/admin/assets',json={'id':key},
                         headers=self.auth).status_code,200)
        self.assertFalse((Path(self.tmp.name)/'media'/(key+'-pages')).exists())

    def test_failed_document_conversion_does_not_publish_asset(self):
        with patch('museum.render', side_effect=ValueError('无法转换')):
            response = self.client.post('/museum/api/admin/upload?name=bad.docx',
                                        data=b'invalid',headers=self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list((Path(self.tmp.name)/'media').iterdir()), [])
        self.assertEqual(self.client.get('/museum/api/admin/catalog',headers=self.auth).json['assets'], {})

    def test_weekly_schedule_uses_start_day_across_midnight(self):
        item={'enabled':True,'rule':rule_for({'repeat':'weekly','from':'2026-11-02',
               'until':'2026-11-02','start':'22:00','end':'02:00','days':[0]})}
        self.assertTrue(active(item,dt.datetime(2026,11,3,1,59)))
        self.assertFalse(active(item,dt.datetime(2026,11,3,2)))
