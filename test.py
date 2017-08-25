# -*- coding: utf-8 -*-
"""Tests for the gcinvoice module.

Run this module as script to perform all tests.

"""

import io
import sys
import subprocess
import re
from decimal import Decimal
import StringIO
import datetime
import optparse
import unittest
import doctest
from yaptu import copier

import gcinvoice

import locale
try:
    locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
    test_locale = True
except locale.Error:
    print("Using module 'locale' for number formatting will not be tested")
    print("because the locale 'de_DE.UTF-8' is not avaible")
    test_locale = False

suite = unittest.TestSuite()


# First add the doctests from the modules.
suite.addTest(doctest.DocTestSuite(gcinvoice))


# Some input data needed in various tests.
template = io.open('testdata/template_in.txt', 'r', encoding='utf-8').read()


# The tests

class TestFuncs(unittest.TestCase):

    """Tests for various functions of the gcinvoice module.

    """

    def testConfigParse(self):
        """Test parsing of configuration files."""
        opt, files = gcinvoice._parse_configfiles(configfiles=['gcinvoicerc'])
        self.assertEqual(files, ['gcinvoicerc'])
        self.assertEqual(opt.__dict__, {
            'templates': {'default': 'invoice_template.tex'}, 'outfiles': {},
            'gcfile': 'gcdata.xml'})
        opt.foobar = 'foobar'
        opt, files = gcinvoice._parse_configfiles(configfiles=['gcinvoicerc'],
                                                  options=opt)
        self.assertEqual(files, ['gcinvoicerc'])
        self.assertEqual(opt.__dict__, {
            'templates': {'default': 'invoice_template.tex'}, 'outfiles': {},
            'gcfile': 'gcdata.xml', 'foobar': 'foobar'})

    def testReadnumber(self):
        """Test reading of rational numbers."""
        self.assertEqual(gcinvoice._readnumber('3/4'), Decimal("0.75"))
        self.assertRaises(AttributeError, gcinvoice._readnumber, 1)
        self.assertRaises(ValueError, gcinvoice._readnumber, '1')
        self.assertRaises(AttributeError, gcinvoice._readnumber, None)

    def testReaddate(self):
        """Test reading of dates."""
        self.assertEqual(gcinvoice._readdate('2002-12-01 00:00:00 +0100'),
                         datetime.date(2002, 12, 1))
        self.assertEqual(gcinvoice._readdate('2002-12-01 00:00:00'),
                         datetime.date(2002, 12, 1))
        self.assertEqual(gcinvoice._readdate('2002-12-01 03:00:00'),
                         datetime.date(2002, 12, 1))
        self.assertEqual(gcinvoice._readdate(None), None)
        self.assertRaises(IndexError, gcinvoice._readdate, '')

    def testReaddatetime(self):
        """Test reading of datetimes."""
        self.assertEqual(gcinvoice._readdatetime('2002-12-01 11:22:33 +0100'),
                         datetime.datetime(2002, 12, 1, 11, 22, 33))
        self.assertRaises(ValueError, gcinvoice._readdatetime,
                          '2002-12-01 11:22:33')
        self.assertEqual(gcinvoice._readdatetime(None), None)
        self.assertRaises(IndexError, gcinvoice._readdatetime, '')

    def testCurrencyformatting(self):
        """Test formatting of monetary values."""
        self.assertEqual(gcinvoice._currencyformatting(Decimal("12.34567"),
                         uselocale=False), u'12.34567')
        self.assertEqual(gcinvoice._currencyformatting(Decimal("12.34567"),
                         uselocale=False, precision=3), u'12.346')
        self.assertEqual(gcinvoice._currencyformatting(Decimal("12.00000"),
                         uselocale=False), u'12.00000')
        self.assertEqual(gcinvoice._currencyformatting(Decimal("12.00000"),
                         uselocale=False, precision=3), u'12.000')
        if test_locale:
            self.assertEqual(gcinvoice._currencyformatting(Decimal("12.34567"),
                             uselocale=True), u'12,35')
            self.assertEqual(gcinvoice._currencyformatting(
                Decimal("8912.34567"), uselocale=True), u'8.912,35')
            self.assertEqual(gcinvoice._currencyformatting(
                Decimal("8912.00000"), uselocale=True), u'8.912,00')
            self.assertEqual(gcinvoice._currencyformatting(
                Decimal("8912.34567"), uselocale=True, dashsymb='-'),
                u'8.912,35')
            self.assertEqual(gcinvoice._currencyformatting(
                Decimal("8912.00000"), uselocale=True, dashsymb='-'),
                u'8.912,-')
            self.assertEqual(gcinvoice._currencyformatting(
                Decimal("8912.00000"), uselocale=True,
                dashsymb=u'\u0562~\u0122'), u'8.912,\u0562~\u0122')

    def testQuantityformatting(self):
        """Test formatting of quantity values."""
        self.assertEqual(gcinvoice._quantityformatting(Decimal("12.34567"),
                         uselocale=False), u'12.34567')
        self.assertEqual(gcinvoice._quantityformatting(Decimal("12.34567"),
                         uselocale=False, precision=3), u'12.346')
        self.assertEqual(gcinvoice._quantityformatting(Decimal("12.00000"),
                         uselocale=False), u'12.00000')
        self.assertEqual(gcinvoice._quantityformatting(Decimal("12.00000"),
                         uselocale=False, precision=3), u'12.000')
        if test_locale:
            self.assertEqual(gcinvoice._quantityformatting(Decimal("12.34567"),
                             uselocale=True), u'12,34567')
            self.assertEqual(gcinvoice._quantityformatting(
                Decimal("8912.34567"), uselocale=True), u'8.912,34567')
            self.assertEqual(gcinvoice._quantityformatting(
                Decimal("8912.00000"), uselocale=True), u'8.912')
            self.assertEqual(gcinvoice._quantityformatting(
                Decimal("8912.34567"), uselocale=True, dashsymb='-'),
                u'8.912,34567')
            self.assertEqual(gcinvoice._quantityformatting(
                Decimal("8912.00000"), uselocale=True, dashsymb='-'),
                u'8.912,-')
            self.assertEqual(gcinvoice._quantityformatting(
                Decimal("8912.00000"), uselocale=True,
                dashsymb=u'\u0562~\u0122'), u'8.912,\u0562~\u0122')


suite.addTest(unittest.makeSuite(TestFuncs))


class TestYaptu(unittest.TestCase):

    """Test of the YAPTU templating engine.

    """

    def testYaptu(self):
        """Test of the YAPTU templating engine."""
        rex = re.compile('@\\{([^}]+)\\}')
        rbe = re.compile('%\\+ ')
        ren = re.compile('%-')
        rco = re.compile('%= ')
        temp_dict = {'a': 'a1', 'b': u'\u01222', 'c': 5, 'li': [5, 4, 3],
                     'di': dict(x=1, y=2)}
        templ_out = StringIO.StringIO()
        testdata_in = io.open(
            'testdata/yaptu_testYaptu_in.txt', 'r', encoding='utf-8').read()
        templ_in = [(line+'\n') for line in testdata_in.split('\n')]
        yaptu = copier(rex, temp_dict, rbe, ren, rco,
                       ouf=templ_out, encoding='utf-8')
        yaptu.copy(templ_in)
        result = templ_out.getvalue()
        templ_out.close()
        testdata_out = io.open(
            'testdata/yaptu_testYaptu_out.txt', 'r',
            encoding='utf-8').read().encode('utf-8')
        self.assertEqual(result, testdata_out)


suite.addTest(unittest.makeSuite(TestYaptu))


class TestMain(unittest.TestCase):

    """Tests of the main Gcinvoice class.

    """

    def setUp(self):
        gcinvoice.Gcinvoice.configfiles = ['gcinvoicerc']
        self.gc = gcinvoice.Gcinvoice()
        self.gc.parse()

    def testParse(self):
        """Test parsing of a Gnucash data file."""
        self.assertEqual(self.gc.customers, {
            'ec6e7eca10bf375752b74aaab55cd75c': {
                'guid': 'ec6e7eca10bf375752b74aaab55cd75c',
                'name': 'Caesar', 'id': 1, 'full_name': 'Gaius Julius Caesar',
                'address': ['Palatin 7', 'Rome']}})
        self.assertEqual(self.gc.vendors, {
            '6b5ef6b315fb583cfc994d0857dc62cf': {
                'guid': '6b5ef6b315fb583cfc994d0857dc62cf',
                'name': 'Crassus', 'id': 1, 'full_name':
                'Marcus Licinius Crassus', 'address': ['Aventin 9', 'Rome']}})
        self.assertEqual(self.gc.terms, {
            'cf9e15a66f6414cda27c0c78449f4bce': {
                'guid': 'cf9e15a66f6414cda27c0c78449f4bce',
                'name': 'Standard', 'desc': '', 'due-days': '30',
                'disc-days': '10', 'discount': Decimal("5")},
            'd1f7440a38bceede661256a9bb5639c7': {
                'guid': 'd1f7440a38bceede661256a9bb5639c7',
                'name': 'Standard', 'desc': '', 'due-days': '30',
                'disc-days': '10', 'discount': Decimal("5")}})
        self.assertEqual(self.gc.entries, {
            'ee4c70d967b0f91f49ded26d578ab6eb': {
                'taxincluded': 0, 'discount_how': 'PRETAX',
                'description': 'With excluded taxes, pretax value discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("1343.5"),
                'amount_raw': Decimal("1000"), 'discount_type': 'VALUE',
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_net': Decimal("995"), 'amount_discount': Decimal("5"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 8, 40),
                'guid': 'ee4c70d967b0f91f49ded26d578ab6eb',
                'amount_taxes': Decimal("348.5"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '799275323663eb1b5fa39350e50ecce5': {
                'taxincluded': 1, 'description': 'With included taxes',
                'discount': None, 'price': Decimal("100"),
                'amount_gross': Decimal("1000.000000000000000000000000"),
                'amount_raw': Decimal("1000"),
                'amount_net': Decimal("730.7692307692307692307692308"),
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_discount': Decimal("0E-25"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 4, 46),
                'guid': '799275323663eb1b5fa39350e50ecce5',
                'amount_taxes': Decimal("269.2307692307692307692307692"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '7ebf2ee4511c70523f4be6f54e39bf6d': {
                'taxincluded': 1, 'discount_how': 'POSTTAX',
                'description': 'With included taxes, posttax percent discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("950"), 'amount_raw': Decimal("1000"),
                'discount_type': 'PERCENT', 'qty': Decimal("10"), 'taxable': 1,
                'action': 'Auftrag',
                'amount_net': Decimal("692.3076923076923076923076923"),
                'amount_discount': Decimal("50"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 12, 52),
                'guid': '7ebf2ee4511c70523f4be6f54e39bf6d',
                'amount_taxes': Decimal("257.6923076923076923076923077"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '4aa395e4642fa95dfccc5542b7aa7631': {
                'taxincluded': 0, 'discount_how': 'POSTTAX',
                'description': 'With excluded taxes, posttax value discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("1345.0"),
                'amount_raw': Decimal("1000"), 'discount_type': 'VALUE',
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_net': Decimal("996.1538461538461538461538462"),
                'amount_discount': Decimal("5"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 13, 17),
                'guid': '4aa395e4642fa95dfccc5542b7aa7631',
                'amount_taxes': Decimal("348.8461538461538461538461538"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '45e9da1003a068299bdf7e52dfadb663': {
                'taxincluded': 1, 'discount_how': 'PRETAX',
                'description': 'With included taxes, pretax value discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("993.5000000000000000000000000"),
                'amount_raw': Decimal("1000"), 'discount_type': 'VALUE',
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_net': Decimal("725.7692307692307692307692308"),
                'amount_discount': Decimal("5"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 9, 23),
                'guid': '45e9da1003a068299bdf7e52dfadb663',
                'amount_taxes': Decimal("267.7307692307692307692307692"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '86c17026397d66a67eb3fd828855dded': {
                'amount_discount': Decimal("50"), 'discount_how': 'PRETAX',
                'description': 'Without taxes, with percent discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("950"), 'amount_raw': Decimal("1000"),
                'discount_type': 'PERCENT', 'qty': Decimal("10"), 'taxable': 0,
                'action': 'Auftrag', 'amount_net': Decimal("950"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 2, 22),
                'guid': '86c17026397d66a67eb3fd828855dded',
                'amount_taxes': Decimal("0")},
            'abb5a554f3cb5036fce1bf821e7903e6': {
                'taxincluded': 1, 'discount_how': 'SAMETIME',
                'description': 'With included taxes, sametime value discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("995"), 'amount_raw': Decimal("1000"),
                'discount_type': 'VALUE', 'qty': Decimal("10"), 'taxable': 1,
                'action': 'Auftrag',
                'amount_net': Decimal("725.7692307692307692307692308"),
                'amount_discount': Decimal("5"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 11, 51),
                'guid': 'abb5a554f3cb5036fce1bf821e7903e6',
                'amount_taxes': Decimal("269.2307692307692307692307692"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            'a56fe2c2a7adc4ee99312ce9139d83b9': {
                'taxincluded': 1, 'discount_how': 'PRETAX',
                'description': 'With included taxes, pretax percent discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("952.5000000000000000000000001"),
                'amount_raw': Decimal("1000"), 'discount_type': 'PERCENT',
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_net': Decimal("694.2307692307692307692307693"),
                'amount_discount': Decimal("36.53846153846153846153846154"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 8, 17),
                'guid': 'a56fe2c2a7adc4ee99312ce9139d83b9',
                'amount_taxes': Decimal("258.2692307692307692307692308"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '57fda35d12aa75708c29fcf7d84e1262': {
                'taxincluded': 0, 'discount_how': 'PRETAX',
                'description': 'With excluded taxes, pretax percent discount',
                'discount': Decimal("5"), 'price': Decimal("100"),
                'amount_gross': Decimal("1285.0"),
                'amount_raw': Decimal("1000"), 'discount_type': 'PERCENT',
                'qty': Decimal("10"), 'taxable': 1, 'action': 'Auftrag',
                'amount_net': Decimal("950"), 'amount_discount': Decimal("50"),
                'date': datetime.date(2008, 2, 22),
                'entered': datetime.datetime(2008, 2, 22, 21, 7, 23),
                'guid': '57fda35d12aa75708c29fcf7d84e1262',
                'amount_taxes': Decimal("335.0"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            'e834556f473510e826b0fd292de5a59e': {
                'amount_discount': Decimal("5"), 'discount_how': 'PRETAX',
                'guid': 'e834556f473510e826b0fd292de5a59e',
                'date': datetime.date(2008, 2, 22), 'taxable': 0,
                'description': 'Without taxes, with value discount',
                'discount_type': 'VALUE', 'price': Decimal("100"),
                'amount_gross': Decimal("995"), 'amount_net': Decimal("995"),
                'amount_raw': Decimal("1000"), 'discount': Decimal("5"),
                'entered': datetime.datetime(2008, 2, 22, 21, 3, 54),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("0")},
            '19144b12c75bafe7af94155986cb3546': {
                'amount_discount': Decimal("5"), 'discount_how': 'SAMETIME',
                'guid': '19144b12c75bafe7af94155986cb3546',
                'date': datetime.date(2008, 2, 22),
                'description': 'With excluded taxes, sametime value discount',
                'discount_type': 'VALUE', 'price': Decimal("100"),
                'amount_gross': Decimal("1345.0"),
                'amount_net': Decimal("995"),
                'amount_raw': Decimal("1000"), 'taxincluded': 0,
                'discount': Decimal("5"),
                'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 11, 28),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("350.0"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '5cec35bbc9d74415c835c11d5fd27397': {
                'amount_discount': Decimal("0"),
                'guid': '5cec35bbc9d74415c835c11d5fd27397',
                'date': datetime.date(2008, 2, 22),
                'description': 'Without taxes and discount',
                'price': Decimal("100"), 'amount_gross': Decimal("1000"),
                'amount_net': Decimal("1000"), 'amount_raw': Decimal("1000"),
                'discount': None, 'taxable': 0,
                'entered': datetime.datetime(2008, 2, 22, 21, 1, 30),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("0")},
            '39a813f604ebccc4abd3cc0a78c40c0f': {
                'amount_discount': Decimal("67.5"), 'discount_how': 'POSTTAX',
                'guid': '39a813f604ebccc4abd3cc0a78c40c0f',
                'date': datetime.date(2008, 2, 22),
                'description': 'With excluded taxes, posttax percent discount',
                'discount_type': 'PERCENT', 'price': Decimal("100"),
                'amount_gross': Decimal("1282.5"),
                'amount_net': Decimal("948.0769230769230769230769231"),
                'amount_raw': Decimal("1000"), 'taxincluded': 0,
                'discount': Decimal("5"), 'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 12, 27),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("334.4230769230769230769230769"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '7461d2f73e7147323918d925af607f08': {
                'amount_discount': Decimal("50"), 'discount_how': 'SAMETIME',
                'guid': '7461d2f73e7147323918d925af607f08',
                'date': datetime.date(2008, 2, 22),
                'description': 'With excluded taxes, '
                    'sametime percent discount',
                'discount_type': 'PERCENT', 'price': Decimal("100"),
                'amount_gross': Decimal("1300.0"),
                'amount_net': Decimal("950"),
                'amount_raw': Decimal("1000"), 'taxincluded': 0,
                'discount': Decimal("5"),
                'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 10, 17),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("350.0"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '23abe4dcbfbadf6761f7e46c14a63aad': {
                'amount_discount': Decimal("0"),
                'guid': '23abe4dcbfbadf6761f7e46c14a63aad',
                'date': datetime.date(2008, 2, 22),
                'description': 'With excluded taxes, without discount',
                'price': Decimal("100"), 'amount_raw': Decimal("1000"),
                'amount_net': Decimal("1000"),
                'amount_gross': Decimal("1350.0"),
                'taxincluded': 0, 'discount': None, 'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 1, 49),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("350.0"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '83b794c691503074e6f5841967a00968': {
                'amount_discount': Decimal("36.53846153846153846153846154"),
                'discount_how': 'SAMETIME',
                'guid': '83b794c691503074e6f5841967a00968',
                'date': datetime.date(2008, 2, 22),
                'description': 'With included taxes, '
                    'sametime percent discount',
                'discount_type': 'PERCENT', 'price': Decimal("100"),
                'amount_gross': Decimal("963.4615384615384615384615385"),
                'amount_net': Decimal("694.2307692307692307692307693"),
                'amount_raw': Decimal("1000"), 'taxincluded': 1,
                'discount': Decimal("5"), 'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 10, 52),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("269.2307692307692307692307692"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '61ca0fab81f70c5384b42dbadf8302ce': {
                'amount_discount': Decimal("5"), 'discount_how': 'POSTTAX',
                'guid': '61ca0fab81f70c5384b42dbadf8302ce',
                'date': datetime.date(2008, 2, 22),
                'description': 'With included taxes, posttax value discount',
                'discount_type': 'VALUE', 'price': Decimal("100"),
                'amount_gross': Decimal("995"),
                'amount_net': Decimal("726.9230769230769230769230769"),
                'amount_raw': Decimal("1000"), 'taxincluded': 1,
                'discount': Decimal("5"), 'taxable': 1,
                'entered': datetime.datetime(2008, 2, 22, 21, 14, 30),
                'qty': Decimal("10"), 'action': 'Auftrag',
                'amount_taxes': Decimal("268.0769230769230769230769231"),
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            '43b45b9376243f2669758cc4b7deae5e': {
                'action': None,
                'discount': None, 'amount_gross': Decimal("26050.0"),
                'amount_net': Decimal("20000"), 'amount_raw': Decimal("20000"),
                'amount_taxes': Decimal("6050.0"),
                'date': datetime.date(2010, 7, 9), 'description': 'Legion',
                'entered': datetime.datetime(2010, 7, 9, 13, 16, 8),
                'guid': '43b45b9376243f2669758cc4b7deae5e',
                'price': Decimal("10000"), 'qty': Decimal("2"), 'taxable': 1,
                'amount_discount': Decimal("0"), 'taxincluded': 0,
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            'f2e465c3d346b706eb317fbc9596cc17': {
                'action': None, 'amount_discount': Decimal("0"),
                'amount_gross': Decimal("76.0"), 'amount_net': Decimal("20"),
                'amount_raw': Decimal("20"), 'amount_taxes': Decimal("56.0"),
                'date': datetime.date(2010, 7, 9), 'description': 'Beer',
                'discount': None,
                'entered': datetime.datetime(2010, 7, 9, 15, 40, 27),
                'guid': 'f2e465c3d346b706eb317fbc9596cc17',
                'price': Decimal("10"), 'qty': Decimal("2"), 'taxable': 1,
                'taxincluded': 0,
                'taxtable':
                    self.gc.taxtables['1b1a9e78db87ffa07886abe977011995']},
            })
        self.assertEqual(self.gc.invoices[1],
                         self.gc.invoices_['31cf0c86220ec3ef67be360f8c4416fb'])
        self.assertEqual(self.gc.invoices, {
            1: {
                'guid': '31cf0c86220ec3ef67be360f8c4416fb',
                'id': 1,
                'owner': self.gc.customers['ec6e7eca10bf375752b74aaab55cd75c'],
                'date_opened': datetime.date(2008, 2, 22),
                'date_posted': datetime.date(2008, 2, 22),
                'terms': self.gc.terms['d1f7440a38bceede661256a9bb5639c7'],
                'notes': 'Items delivered in March', 'job': None,
                'currency': 'EUR', 'billing_id': None, '_warndiscount': True,
                'entries': [
                    self.gc.entries['5cec35bbc9d74415c835c11d5fd27397'],
                    self.gc.entries['23abe4dcbfbadf6761f7e46c14a63aad'],
                    self.gc.entries['86c17026397d66a67eb3fd828855dded'],
                    self.gc.entries['e834556f473510e826b0fd292de5a59e'],
                    self.gc.entries['799275323663eb1b5fa39350e50ecce5'],
                    self.gc.entries['57fda35d12aa75708c29fcf7d84e1262'],
                    self.gc.entries['a56fe2c2a7adc4ee99312ce9139d83b9'],
                    self.gc.entries['ee4c70d967b0f91f49ded26d578ab6eb'],
                    self.gc.entries['45e9da1003a068299bdf7e52dfadb663'],
                    self.gc.entries['7461d2f73e7147323918d925af607f08'],
                    self.gc.entries['83b794c691503074e6f5841967a00968'],
                    self.gc.entries['19144b12c75bafe7af94155986cb3546'],
                    self.gc.entries['abb5a554f3cb5036fce1bf821e7903e6'],
                    self.gc.entries['39a813f604ebccc4abd3cc0a78c40c0f'],
                    self.gc.entries['7ebf2ee4511c70523f4be6f54e39bf6d'],
                    self.gc.entries['4aa395e4642fa95dfccc5542b7aa7631'],
                    self.gc.entries['61ca0fab81f70c5384b42dbadf8302ce'],
                    ]},
            2: {
                'terms': None, 'notes': 'Olives, good', 'entries': [],
                'date_posted': datetime.date(2010, 7, 9), 'currency': 'EUR',
                'job': None, 'date_opened': datetime.date(2010, 7, 9),
                'owner': self.gc.vendors['6b5ef6b315fb583cfc994d0857dc62cf'],
                'billing_id': '987',
                'guid': 'feef793eae7001905aa1976469b1304e',
                'id': 2},
            3: {
                'terms': self.gc.terms['d1f7440a38bceede661256a9bb5639c7'],
                'notes': 'Two Legions for Caesar',
                'entries': [
                    self.gc.entries['43b45b9376243f2669758cc4b7deae5e']],
                'date_posted': datetime.date(2010, 7, 9), 'currency': 'EUR',
                'job': self.gc.jobs['6a89fad0d72a7071e9213a4f54a76cab'],
                'date_opened': datetime.date(2010, 7, 9),
                'owner': self.gc.customers['ec6e7eca10bf375752b74aaab55cd75c'],
                'billing_id': None,
                'guid': 'a96b54870cbe6060c270b2652d35e710', 'id': 3},
            4: {
                'terms': None, 'notes': 'Wine for the Legions', 'entries': [],
                'date_posted': datetime.date(2010, 7, 9), 'currency': 'EUR',
                'job': self.gc.jobs['0568d5e3911c33eb8761f9177554d10e'],
                'date_opened': datetime.date(2010, 7, 9), 'id': 4,
                'owner': self.gc.vendors['6b5ef6b315fb583cfc994d0857dc62cf'],
                'billing_id': '010203',
                'guid': '412a79664af3e15cfa481db82459773a'},
            5: {
                'terms': self.gc.terms['d1f7440a38bceede661256a9bb5639c7'],
                'notes': 'Some beer', 'entries': [
                    self.gc.entries['f2e465c3d346b706eb317fbc9596cc17'],
                    ],
                'date_posted': datetime.date(2010, 7, 9), 'currency': 'EUR',
                'job': None, 'date_opened': datetime.date(2010, 7, 9),
                'owner': self.gc.customers['ec6e7eca10bf375752b74aaab55cd75c'],
                'billing_id': '445',
                'guid': 'eaa069411f46260c90db6d852984861d',
                'id': 5},
            })
        for t in self.gc.taxtables.itervalues():
            # the entries are in random order, bad to test.
            del t['entries']
        self.assertEqual(self.gc.taxtables, {
            'f374d86b246da3603d0b9665d44fec9c': {
                'guid': 'f374d86b246da3603d0b9665d44fec9c',
                'name': 'VAT', 'percent_sum': Decimal("30"),
                'value_sum': Decimal("50")},
            '1b1a9e78db87ffa07886abe977011995': {
                'guid': '1b1a9e78db87ffa07886abe977011995',
                'name': 'VAT', 'percent_sum': Decimal("30"),
                'value_sum': Decimal("50")}})

    def testCreateInvoice(self):
        """Test creation of an invoice."""
        self.gc.options.quantities_uselocale = False
        self.gc.options.quantities_precision = 1
        self.gc.options.currency_uselocale = False
        self.gc.options.currency_precision = 3
        outf = StringIO.StringIO()
        self.gc.createInvoice(1, outfile=outf, template=template)
        result = outf.getvalue()
        outf.close()
        self.assertEqual(result, io.open(
            'testdata/main_createInvoice1_out.txt', 'r',
            encoding='utf-8').read().encode('utf-8'))

        if test_locale:
            self.gc.options.quantities_uselocale = True
            self.gc.options.currency_uselocale = True
            outf = StringIO.StringIO()
            self.gc.createInvoice(1, outfile=outf, template=template)
            result = outf.getvalue()
            outf.close()
            self.assertEqual(result, io.open(
                'testdata/main_createInvoice2_out.txt', 'r',
                encoding='utf-8').read().encode('utf-8'))

        def cformat(val):
            return u"dummy"
        self.gc.options.quantities_uselocale = False
        self.gc.options.quantities_precision = 1
        self.gc.options.cformat = cformat
        outf = StringIO.StringIO()
        self.gc.createInvoice(1, outfile=outf, template=template)
        result = outf.getvalue()
        outf.close()
        self.assertEqual(result, io.open(
            'testdata/main_createInvoice3_out.txt', 'r',
            encoding='utf-8').read().encode('utf-8'))


suite.addTest(unittest.makeSuite(TestMain))


class TestScript(unittest.TestCase):

    """Tests for running gcinvoice as a script.

    """

    def testCreateInvoice(self):
        """Test of the createInvoice function."""
        options = optparse.Values()
        options.gcfile = 'gcdata.xml'
        options.quantities_uselocale = False
        options.quantities_precision = 1
        options.currency_uselocale = False
        options.currency_precision = 3
        outf = StringIO.StringIO()
        gcinvoice.createInvoice(1, template=template, outfile=outf,
                                options=options)
        result = outf.getvalue()
        outf.close()
        self.assertEqual(result, io.open(
            'testdata/script_createInvoice_out.txt', 'r',
            encoding='utf-8').read().encode('utf-8'))

    def testScriptrun(self):
        """Test of running gcinvoice as a script."""
        if not test_locale:
            return
        cmd = "%s gcinvoice.py -g gcdata.xml -t invoice_template.tex 1" % \
            (sys.executable,)
        stdout, stderr = subprocess.Popen(
            cmd.split(), stdout=subprocess.PIPE,
            env=dict(LC_ALL='de_DE.UTF-8')).communicate()

        self.assertEqual(stdout, io.open(
            'testdata/script_scriptrun_out.tex').read().encode('utf-8'))


suite.addTest(unittest.makeSuite(TestScript))


# Run the tests

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite)
