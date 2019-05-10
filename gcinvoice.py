#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Module to parse Gnucash data files and to create invoices.

This module provides a class 'Gcinvoice' used to parse Gnucash data files and
to create invoices from this data and from template files. Currently only the
data useful for invoices is extracted. The convience function 'createInvoice'
uses 'Gcinvoice' to create directly an invoice, and is called if this module is
run as script. Finally there is an Exception class 'GcinvoiceError'. These are
the only 3 names imported by 'import * from gcinvoice'.

"""
# Needed for Python2 compatibility, remove later
from __future__ import division
from __future__ import unicode_literals
from builtins import object, str

__version__ = '0.1.5'

import argparse
import codecs
import configparser
import copy
import datetime
from decimal import Decimal
import functools
import gzip
import io
import locale
import logging
from operator import itemgetter
import os
import re
from string import Template
import sys
import textwrap

from yaptu import copier

get0 = itemgetter(0)
get_entered = itemgetter('entered')

locale.setlocale(locale.LC_ALL, '')
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET


# The main classes.

class GcinvoiceError(Exception):
    """Exceptions raised by this module."""
    pass


class Gcinvoice(object):

    """Class to parse Gnucash data files and to create invoices.

    Methods:
        parse -- Parse Gnucash data files.
        createInvoice -- Create an invoice from a template.

    """

    configfiles = ['/etc/gcinvoicerc', os.path.expanduser('~/.gcinvoicerc'),
                   'gcinvoicerc']

    _xmlns_uris = {
            'gnc': "http://www.gnucash.org/XML/gnc",
            'cust': "http://www.gnucash.org/XML/cust",
            'vendor': "http://www.gnucash.org/XML/vendor",
            'addr': "http://www.gnucash.org/XML/addr",
            'taxtable': "http://www.gnucash.org/XML/taxtable",
            'job': "http://www.gnucash.org/XML/job",
            'invoice': "http://www.gnucash.org/XML/invoice",
            'owner': "http://www.gnucash.org/XML/owner",
            'ts': "http://www.gnucash.org/XML/ts",
            'cmdty': "http://www.gnucash.org/XML/cmdty",
            'tte': "http://www.gnucash.org/XML/tte",
            'billterm': "http://www.gnucash.org/XML/billterm",
            'bt-days': "http://www.gnucash.org/XML/bt-days",
            'entry': "http://www.gnucash.org/XML/entry",
        }

    _xmlns_re = re.compile(r'([_a-z][-_a-z0-9]*):')

    def __init__(self, options=None):

        """Create a Gcinvoice instance.

        Arguments:
            options -- Object holding options. Options used here are:
                configfiles -- Configuration file(s) holding default options.
                logname -- Name for the logger.
                loglevel -- Level of the logger.
                See the other methods for other used options.

        """

        configfiles = list(self.configfiles)
        optconffiles = getattr(options, 'configfiles', [])
        try:
            configfiles.extend(optconffiles)
        except Exception:
            configfiles.append(optconffiles)
        self.options, parsed_files = _parse_configfiles(
                configfiles=configfiles, options=options)
        logname = getattr(self.options, 'logname', None) or 'gcinvoice'
        self.logger = logging.getLogger(logname)
        logging.basicConfig()
        loglevel = getattr(self.options, 'loglevel', None)
        if loglevel is not None:
            self.logger.setLevel(loglevel)
        self.logger.info("Parsed configuration files [%s], Gcinvoice instance "
                         "created" % ", ".join(parsed_files))

    def parse(self, gcfile=None):
        """Parse a Gnucash file.

        Currently only the data useful for invoices is extracted.

        Arguments:
            gcfile -- the file containing Gnucash data.
        Options from self.options used by this method:
            gcfile -- the file containing Gnucash data.

        """

        if not gcfile:
            gcfile = getattr(self.options, 'gcfile', None)
        if not gcfile:
            self.logger.error("No gcfile given.")
            raise GcinvoiceError("No gcfile given.")
        try:
            self.gctree = ET.parse(gcfile)
        except SyntaxError:
            try:
                gcfile_ = gzip.open(gcfile)
                self.gctree = ET.parse(gcfile_)
                gcfile_.close()
            except Exception:
                self.logger.error("Could not parse file [%s]." % gcfile)
                raise

        ns = self._xmlns_qualify
        book = self.gctree.find(ns('gnc:book'))

        self.customers = {}
        for cust in book.findall(ns('gnc:GncCustomer')):
            try:
                custdict = dict(address=[])
                custdict['guid'] = cust.findtext(ns('cust:guid'))
                custdict['name'] = cust.findtext(ns('cust:name'))
                custdict['id'] = intid(cust.findtext(ns('cust:id')))
                for a in cust.findall(ns('cust:addr/*')):
                    if a.tag == ns('addr:email'):
                        custdict['email'] = a.text
                    elif a.tag == ns('addr:name'):
                        custdict['full_name'] = a.text
                    elif a.tag.startswith(ns('addr:addr')):
                        custdict['address'].append((a.tag, a.text))
                custdict['address'].sort(key=get0)
                custdict['address'] = [x[1] for x in custdict['address']]
                self.customers[custdict['guid']] = custdict
            except Exception:
                self.logger.warn("Problem parsing GncCustomer [%s]" %
                                 ET.tostring(cust), exc_info=True)
                continue

        self.vendors = {}
        for vendor in book.findall(ns('gnc:GncVendor')):
            try:
                vendordict = dict(address=[])
                vendordict['guid'] = vendor.findtext(ns('vendor:guid'))
                vendordict['name'] = vendor.findtext(ns('vendor:name'))
                vendordict['id'] = intid(vendor.findtext(ns('vendor:id')))
                for a in vendor.findall(ns('vendor:addr/*')):
                    if a.tag == ns('addr:email'):
                        vendordict['email'] = a.text
                    elif a.tag == ns('addr:name'):
                        vendordict['full_name'] = a.text
                    elif a.tag.startswith(ns('addr:addr')):
                        vendordict['address'].append((a.tag, a.text))
                vendordict['address'].sort(key=get0)
                vendordict['address'] = [x[1] for x in vendordict['address']]
                self.vendors[vendordict['guid']] = vendordict
            except Exception:
                self.logger.warn("Problem parsing GncVendor [%s]" %
                                 ET.tostring(vendor), exc_info=True)
                continue

        self.terms = {}
        for term in book.findall(ns('gnc:GncBillTerm')):
            try:
                termdict = dict()
                termdict['guid'] = term.findtext(ns('billterm:guid'))
                termdict['name'] = term.findtext(ns('billterm:name'))
                termdict['desc'] = term.findtext(ns('billterm:desc'))
                termdict['due-days'] = term.findtext(
                        ns('billterm:days/bt-days:due-days'))
                termdict['disc-days'] = term.findtext(
                        ns('billterm:days/bt-days:disc-days'))
                discount = term.findtext(ns('billterm:days/bt-days:discount'))
                if discount is not None:
                    discount = _readnumber(discount)
                termdict['discount'] = discount
                self.terms[termdict['guid']] = termdict
            except Exception:
                self.logger.warn("Problem parsing GncBillTerm [%s]" %
                                 ET.tostring(term), exc_info=True)
                continue

        self.taxtables = {}
        for tax in book.findall(ns('gnc:GncTaxTable')):
            try:
                taxdict = dict(entries=[])
                taxdict['guid'] = tax.findtext(ns('taxtable:guid'))
                taxdict['name'] = tax.findtext(ns('taxtable:name'))
                taxdict['percent_sum'] = Decimal(0)
                taxdict['value_sum'] = Decimal(0)
                for te in tax.findall(
                        ns('taxtable:entries/gnc:GncTaxTableEntry')):
                    tedict = dict()
                    try:
                        tedict['type'] = te.findtext(ns('tte:type'))
                        tedict['amount'] = _readnumber(
                                te.findtext(ns('tte:amount')))
                        if tedict['type'] == 'PERCENT':
                            taxdict['percent_sum'] += tedict['amount']
                        elif tedict['type'] == 'VALUE':
                            taxdict['value_sum'] += tedict['amount']
                        else:
                            self.logger.warn("Invalid tte:type [%s]" %
                                             tedict['type'])
                            raise GcinvoiceError("Invalid tte:type")
                    except Exception:
                        self.logger.warn(
                                "Problem parsing GncTaxTableEntry [%s]" %
                                ET.tostring(te), exc_info=True)
                        raise
                    taxdict['entries'].append(tedict)
            except Exception:
                self.logger.warn("Problem parsing GncTaxTable [%s]" %
                                 ET.tostring(tax), exc_info=True)
                continue
            self.taxtables[taxdict['guid']] = taxdict

        self.jobs = {}
        for job in book.findall(ns('gnc:GncJob')):
            try:
                jobdict = dict()
                jobdict['guid'] = job.findtext(ns('job:guid'))
                jobdict['name'] = job.findtext(ns('job:name'))
                jobdict['id'] = intid(job.findtext(ns('job:id')))
                jobdict['reference'] = job.findtext(ns('job:reference'))
                ownerguid = job.findtext(ns('job:owner/owner:id'))
                ownertype = job.findtext(ns('job:owner/owner:type'))
                if ownertype == 'gncVendor':
                    jobdict['owner'] = self.vendors.get(ownerguid, None)
                elif ownertype == 'gncCustomer':
                    jobdict['owner'] = self.customers.get(ownerguid, None)
                self.jobs[jobdict['guid']] = jobdict
            except Exception:
                self.logger.warn("Problem parsing Gncjob [%s]" %
                                 ET.tostring(job), exc_info=True)
                continue

        self.invoices = {}
        self.invoices_ = {}
        for invc in book.findall(ns('gnc:GncInvoice')):
            invcdict = dict()
            try:
                invcdict['guid'] = invc.findtext(ns('invoice:guid'))
                invcdict['id'] = intid(invc.findtext(ns('invoice:id')))
                invcdict['billing_id'] = invc.findtext(
                    ns('invoice:billing_id'))
                invcdict['job'] = None
                ownerguid = invc.findtext(ns('invoice:owner/owner:id'))
                ownertype = invc.findtext(ns('invoice:owner/owner:type'))
                if ownertype == 'gncVendor':
                    invcdict['owner'] = self.vendors.get(ownerguid, None)
                elif ownertype == 'gncCustomer':
                    invcdict['owner'] = self.customers.get(ownerguid, None)
                elif ownertype == 'gncJob':
                    invcdict['job'] = self.jobs.get(ownerguid, None)
                    if invcdict['job']:
                        invcdict['owner'] = invcdict['job'].get('owner', None)
                invcdict['date_opened'] = _readdate(invc.findtext(
                    ns('invoice:opened/ts:date')))
                invcdict['date_posted'] = _readdate(invc.findtext(
                    ns('invoice:posted/ts:date')))
                termsguid = invc.findtext(ns('invoice:terms'))
                invcdict['terms'] = self.terms.get(termsguid, None)
                invcdict['notes'] = invc.findtext(ns('invoice:notes'))
                invcdict['currency'] = invc.findtext(
                        ns('invoice:currency/cmdty:id'))

                invcdict['owner']['id'] = str(invcdict['owner']['id']).zfill(5)
            except Exception:
                self.logger.warn("Problem parsing GncInvoice [%s]" %
                                 ET.tostring(invc), exc_info=True)
                continue
            invcdict['entries'] = []   # to be filled later parsing entries
            self.invoices[invcdict['id']] = invcdict
            self.invoices_[invcdict['guid']] = invcdict

        self.entries = {}
        # do this until the XPath 'tag[subtag]' expression works (ET >= 1.3).
        for entry in book.findall(ns('gnc:GncEntry')):
            try:
                invoiceguid = entry.findtext(ns('entry:invoice'))
                if not invoiceguid:
                    continue
                try:
                    invoiceentries = self.invoices_[invoiceguid]['entries']
                except KeyError:
                    self.logger.warn("Cannot find GncInvoice for guid [%s]"
                                     "refered in GncEntry [%s]" %
                                     (invoiceguid, ET.tostring(entry)),
                                     exc_info=True)
                    continue
                entrydict = dict()
                entrydict['guid'] = entry.findtext(ns('entry:guid'))
                entrydict['date'] = _readdate(entry.findtext(
                    ns('entry:date/ts:date')))
                entrydict['entered'] = _readdatetime(entry.findtext(
                    ns('entry:entered/ts:date')))
                entrydict['description'] = entry.findtext(
                        ns('entry:description'))
                entrydict['action'] = entry.findtext(ns('entry:action'))
                entrydict['qty'] = _readnumber(entry.findtext(
                        ns('entry:qty')))
                entrydict['price'] = _readnumber(entry.findtext(
                        ns('entry:i-price')))
                entrydict['discount'] = entry.findtext(ns('entry:i-discount'))
                if entrydict['discount'] is not None:
                    entrydict['discount'] = _readnumber(entrydict['discount'])
                    entrydict['discount_type'] = entry.findtext(
                            ns('entry:i-disc-type'))
                    entrydict['discount_how'] = entry.findtext(
                            ns('entry:i-disc-how'))
                entrydict['taxable'] = int(entry.findtext(
                            ns('entry:i-taxable')))
                if entrydict['taxable']:
                    entrydict['taxincluded'] = int(entry.findtext(
                            ns('entry:i-taxincluded')))
                    taxtable = entry.findtext(ns('entry:i-taxtable'))
                    if taxtable:
                        try:
                            entrydict['taxtable'] = self.taxtables[taxtable]
                        except KeyError:
                            self.logger.warn("Cannot find GncTaxTable for guid"
                                             " [%s] refered in GncEntry [%s]" %
                                             (taxtable, ET.tostring(entry)),
                                             exc_info=True)
                            continue
            except Exception:
                self.logger.warn("Problem parsing GncEntry [%s]" %
                                 ET.tostring(entry), exc_info=True)
                continue
            try:
                self._calcTaxDiscount(entrydict)
            except GcinvoiceError as msg:
                self.logger.error(msg)
                continue
            if entrydict.get('_warndiscount', False):
                del entrydict['_warndiscount']
                self.invoices_[invoiceguid]['_warndiscount'] = True
            self.entries[entrydict['guid']] = entrydict
            invoiceentries.append(entrydict)
        for iv in self.invoices.values():
            iv['entries'].sort(key=get_entered)

        self.logger.info("Successfully parsed Gnucash data file '%s'." %
                         gcfile)

    def getInvoice(self, invoiceid):
        invoiceid = intid(invoiceid)
        try:
            return self.invoices[invoiceid]
        except KeyError:
            self.logger.error("No invoice found for invoiceid [%s]" %
                              invoiceid)
            raise GcinvoiceError("No invoice found for invoiceid [%s]" %
                                 invoiceid)

    def prepareInvoice(self, invc):
        if invc.get('_warndiscount', False):
            self.logger.warn("The invoice contains POSTTAX discounts, which "
                             "are calculated differenty in gcinvoice "
                             "and Gnucash")
        invc['amount_net'] = sum(x['amount_net'] for x in invc['entries'])
        invc['amount_gross'] = sum(x['amount_gross'] for x in invc['entries'])
        invc['amount_taxes'] = sum(x['amount_taxes'] for x in invc['entries'])

        uselocale_qty = getattr(self.options, 'quantities_uselocale', True)
        precision_qty = getattr(self.options, 'quantities_precision', None)
        dashsymb_qty = getattr(self.options, 'quantities_dashsymb', None)
        qformat = getattr(self.options, 'qformat', None)
        uselocale_curr = getattr(self.options, 'currency_uselocale', True)
        precision_curr = getattr(self.options, 'currency_precision', None)
        dashsymb_curr = getattr(self.options, 'currency_dashsymb', None)
        cformat = getattr(self.options, 'cformat', None)
        invc['_currencyformatting'] = _currencyformatting
        invc['_quantityformatting'] = _quantityformatting
        cformat = invc['cformat'] = cformat or functools.partial(
                _currencyformatting, uselocale=uselocale_curr,
                precision=precision_curr, dashsymb=dashsymb_curr)
        qformat = invc['qformat'] = qformat or functools.partial(
                _quantityformatting, uselocale=uselocale_qty,
                precision=precision_qty, dashsymb=dashsymb_qty)
        invc['Decimal'] = Decimal
        for x in ['amount_net', 'amount_gross', 'amount_taxes']:
            invc["%s_" % x] = invc[x]
            invc[x] = cformat(invc[x])
        for e in invc['entries']:
            for x in ['price', 'amount_raw', 'amount_net', 'amount_gross',
                      'amount_taxes', 'amount_discount']:
                e["%s_" % x] = e[x]
                e[x] = cformat(e[x])
            for x in ['qty']:
                e["%s_" % x] = e[x]
                e[x] = qformat(e[x])
            if e['discount'] is not None:
                e['discount_'] = e['discount']
                if e['discount_type'] == 'PERCENT':
                    e['discount'] = cformat(e['discount'])
                else:
                    e['discount'] = qformat(e['discount'])

    def getTemplate(self, template, copier_fun):
        if template is None:
            self.logger.error("No template given.")
            raise GcinvoiceError("No template given.")
        readfromfile = True
        if isinstance(template, str):
            # The name of the template file is itself a template in order to
            # select different templates depending on the invoice.
            templ_ = io.StringIO()
            cop = copier_fun(templ_)
            cop.copy([template])
            templ = templ_.getvalue()
            templ_.close()
            try:
                templ = io.open(templ, 'r', encoding='utf-8')
                self.logger.info("Using file [%s] as template" % templ)
            except Exception:
                self.logger.info("The given template [%s] is not readable, "
                                 "trying to use it directly as string..." %
                                 templ,
                                 exc_info=True)
                try:
                    templ = [(line+'\n') for line in template.split('\n')]
                    readfromfile = False
                except Exception:
                    self.logger.error("The given template [%s] is neither a "
                                      "readable file, nor a readable string" %
                                      template,
                                      exc_info=True)
                    raise GcinvoiceError("The template is neither a file nor a"
                                         " string")
        else:
            templ = template

        if readfromfile:
            self.logger.info("Using [%s] as file object" % templ)
            templ = templ.readlines()

        return templ

    def getOutfile(self, outfile, copier_fun):
        if isinstance(outfile, str):
            # The name of the outfile is itself a template in order to
            # select different outfiles depending on the invoice.
            outf_ = io.StringIO()
            cop = copier_fun(outf_)
            cop.copy([outfile])
            outfile = outf_.getvalue()
            outf_.close()
            try:
                outf = io.open(outfile, 'w', encoding='utf-8')
            except Exception:
                self.logger.error("Cannot open [%s] for writing" % outfile,
                                  exc_info=True)
                raise
            self.logger.info("Using [%s] as outfile" % outfile)
        elif not outfile:
            # UTF-8 conversion needed for Python2,
            # remove when dropping support for it
            if sys.stdout.encoding != 'UTF-8':
                UTF8Writer = codecs.getwriter('utf8')
                outf = UTF8Writer(sys.stdout)
            else:
                outf = sys.stdout

            self.logger.info("Using stdout as outfile")
        else:
            outf = outfile
            self.logger.info("Using [%s] directly as outfile object")

        return outf

    def getYaptuCopierFun(self, invoice):
        rex = re.compile(getattr(self.options, 'regex_rex', None) or
                         '@\\{([^}]+)\\}')
        rbe = re.compile(getattr(self.options, 'regex_rbe', None) or '%\\+')
        ren = re.compile(getattr(self.options, 'regex_ren', None) or '%-')
        rco = re.compile(getattr(self.options, 'regex_rco', None) or '%= ')

        def handle(expr):
            self.logger.warn("Cannot do template for expression [%s]" % expr,
                             exc_info=True)
            return expr

        def copier_fun(outf):
            return copier(rex, invoice, rbe, ren, rco, ouf=outf, handle=handle)

        return copier_fun

    def createInvoice(self, invoiceid, template=None, outfile=None):
        """Create an invoice from the parsed Gnucash data.

        Arguments:
            invoiceid -- Id of the invoice to extract from Gnucash. A string
                         or an integer.
            template -- Name of the invoice template file, or list of lines.
            outfile -- File name for the generated invoice, default is stdout.
        Options from self.options used by this method:
            quantities_uselocale -- Format quantity values using the locale
                setting.
            currency_uselocale -- Format currency values using the locale
                setting.
            quantities_precision -- Used decimal precision for quantities.
            currency_precision -- Used decimal precision for currencies.
            quantities_dashsymb -- Replace a zero fractional part of quantity
                values with this symbol, but only if not None, and if
                uselocale. Example: '12.00' -> '12.-'.
            currency_dashsymb -- As quantities_dashsymb for currency values.
            qformat -- Function to format quantity values, overrides
                quantities_*, should take a Decimal as argument and return an
                unicode string.
            cformat -- Function to format currency values, overrides
                currency_*, should take a Decimal as argument and return an
                unicode string.
            templates -- Dictionary of invoice template file names; keys are
                the 'owner' values of the invoice, or 'default'.
            outfile -- Name of the file to write the invoice out.
            regex_rex -- Expression regex used by the template engine.
            regex_rbe -- Begin statement regex.
            regex_ren -- End statement regex.
            regex_rco -- Continuation statement regex.

        """

        invoice = copy.deepcopy(self.getInvoice(invoiceid))

        self.prepareInvoice(invoice)

        copier_fun = self.getYaptuCopierFun(invoice)

        try:
            ownername = invoice['owner']['name']
        except Exception:
            ownername = None

        template = template or \
            self.options.templates.get(ownername, None) or \
            self.options.templates.get('default', None)
        templ = self.getTemplate(template, copier_fun)

        outfile = outfile or \
            self.options.outfiles.get(ownername, None) or \
            self.options.outfiles.get('default', None)
        outf = self.getOutfile(outfile, copier_fun)

        cop = copier_fun(outf)

        try:
            cop.copy(templ)
            if not isinstance(outf, io.StringIO):
                outf.close()
        except Exception:
            self.logger.error("Error in template", exc_info=True)
            raise

    def _xmlns_qualify(self, xmlnsstring):

        """Return a xmls qualified string to use with Elementtree.

        The templ is transformed from 'ns:tag' to '{_ns}tag' using
        self.xmlns_uris to map ns to _ns.

        Arguments:
            xmlnsstring -- qualified string to use as XPath expression.

        """
        # 'gnc:foobar' -> '{$gnc}foobar' -> '{http://....}foobar'
        templ = self._xmlns_re.sub(r'{$\1}', xmlnsstring)
        return _MyTemplate(templ).safe_substitute(self._xmlns_uris)

    @staticmethod
    def _calcTaxDiscount(entry):

        """Calculate taxes and discounts for an invoice entry.

        Arguments:
            entry -- Dictionary of an invoice entry. These calculed values
                     are put back into this dictionary:
                amount_raw: Product of qty and price.
                amount_discount: Amount (value) of the total discount.
                amount_net: Amount including the discount w/o taxes.
                amount_gross: Amount including the discount with taxes.
                amount_taxes: Amount of the total taxes.
        Example:
            >>> g = Gcinvoice()
            >>> entry = dict(qty=3, price=Decimal('0.4'), discount=10,
            ...     discount_type='PERCENT', discount_how='PRETAX')
            >>> g._calcTaxDiscount(entry)
            >>> entry == dict(qty=3, price=Decimal('0.4'), discount=10,
            ...     discount_type='PERCENT', discount_how='PRETAX',
            ...     amount_raw=Decimal("1.2"),
            ...     amount_discount=Decimal("0.12"),
            ...     amount_gross=Decimal("1.08"),
            ...     amount_net=Decimal("1.08"),
            ...     amount_taxes=Decimal("0.00"))
            True

        """
        amount_raw = entry['amount_raw'] = entry['qty'] * entry['price']
        if not entry.get('taxable', None) or not entry.get('taxtable', None):
            taxtable = dict(percent_sum=Decimal(0), value_sum=Decimal(0))
            taxincluded = 0
        else:
            taxtable = entry['taxtable']
            taxincluded = entry['taxincluded']
        if not entry.get('discount', None):
            discount_how = 'PRETAX'
            discount_type = 'PERCENT'
            discount = Decimal(0)
        else:
            discount_how = entry['discount_how']
            discount_type = entry['discount_type']
            discount = entry['discount']
        if discount_how not in ('PRETAX', 'SAMETIME', 'POSTTAX'):
            raise GcinvoiceError("Unknown discount how [%s] in entry [%s]" %
                                 (discount_how, entry['guid']))
        if discount_type not in ('PERCENT', 'VALUE'):
            raise GcinvoiceError("Unknown discount type [%s] in entry [%s]" %
                                 (discount_type, entry['guid']))

        if taxincluded:
            if discount_how == 'POSTTAX':
                if discount_type == 'VALUE':
                    entry['amount_discount'] = discount
                else:
                    entry['amount_discount'] = discount * amount_raw / 100
                if entry['amount_discount']:
                    entry['_warndiscount'] = True
                entry['amount_gross'] = amount_raw - entry['amount_discount']
                entry['amount_net'] = (
                    entry['amount_gross'] -
                    taxtable['value_sum']) / (
                        1 + taxtable['percent_sum'] / 100)
            else:
                amount_raw_net = (amount_raw - taxtable['value_sum']) / (
                        1 + taxtable['percent_sum'] / 100)
                if discount_type == 'VALUE':
                    entry['amount_discount'] = discount
                else:
                    entry['amount_discount'] = discount * amount_raw_net / 100
                entry['amount_net'] = amount_raw_net - entry['amount_discount']
                if discount_how == 'PRETAX':
                    entry['amount_gross'] = (
                        entry['amount_net'] *
                        (1 + taxtable['percent_sum'] / 100) +
                        taxtable['value_sum'])
                elif discount_how == 'SAMETIME':
                    entry['amount_gross'] = amount_raw - \
                        entry['amount_discount']
                else:
                    raise AssertionError

        else:
            if discount_how == 'POSTTAX':
                amount_raw_gross = amount_raw * (
                    1 + taxtable['percent_sum']/100) + taxtable['value_sum']
                if discount_type == 'VALUE':
                    entry['amount_discount'] = discount
                else:
                    entry['amount_discount'] = discount*amount_raw_gross / 100
                if entry['amount_discount']:
                    entry['_warndiscount'] = True
                entry['amount_gross'] = amount_raw_gross - \
                    entry['amount_discount']
                entry['amount_net'] = (
                    entry['amount_gross'] -
                    taxtable['value_sum']) / (
                    1 + (taxtable['percent_sum'] / 100))
            else:
                if discount_type == 'VALUE':
                    entry['amount_discount'] = discount
                else:
                    entry['amount_discount'] = discount * amount_raw / 100
                entry['amount_net'] = amount_raw - entry['amount_discount']
                if discount_how == 'PRETAX':
                    entry['amount_gross'] = entry['amount_net'] * (
                         1 + taxtable['percent_sum'] / 100) + \
                        taxtable['value_sum']
                elif discount_how == 'SAMETIME':
                    amount_raw_gross = amount_raw * (
                        1 + taxtable['percent_sum'] / 100) + \
                        taxtable['value_sum']
                    entry['amount_gross'] = amount_raw_gross - \
                        entry['amount_discount']
                else:
                    raise AssertionError
        entry['amount_taxes'] = entry['amount_gross'] - entry['amount_net']


# Helper functions and classes.

def _ensure_unicode(somestring):
    """UTF-8 conversion needed for Python2,

    Remove when dropping support for it
    """
    if somestring and not isinstance(somestring, str):
        return somestring.decode('utf-8')

    return somestring


def _parse_configfiles(configfiles=None, options=None):
    """Parse configuration files.

    The pair 'options object, list of parsed files' is returned.

    Arguments:
        configfiles -- Sequence of file names to parse.
        options -- Object to hold the configuration attributes, it is updated
                    and returned.

    """
    options = options or argparse.Namespace()
    filenames = list(configfiles) if configfiles else []
    config = configparser.RawConfigParser()
    parsed_files = config.read(filenames)
    try:
        for k, v in config.items('GENERAL'):
            if getattr(options, k, None) is None:
                setattr(options, _ensure_unicode(k), _ensure_unicode(v))
    except configparser.NoSectionError:
        pass
    for section in 'TEMPLATES', 'OUTFILES':
        d = getattr(options, section.lower(), dict())
        try:
            for k, v in config.items(section):
                d.setdefault(_ensure_unicode(k), _ensure_unicode(v))
        except configparser.NoSectionError:
            pass
        finally:
            setattr(options, section.lower(), d)

    return options, parsed_files


def _readnumber(val):
    """Return the value as Decimal.

    Arguments:
        val -- A string "nominator/denominator".
    Example:
        >>> _readnumber('3/4') == Decimal("0.75")
        True

    """
    n, d = [Decimal(x) for x in val.split('/', 1)]
    return n / d


def _readdate(timestring):
    """Get a date object from a Gnucash datetime string.

    Arguments:
        timestring -- String representing a datetime.
    Example:
        >>> _readdate("2002-12-01 00:00:00 +0100")
        datetime.date(2002, 12, 1)

    """
    if timestring is None:
        return None
    return datetime.datetime.strptime(timestring.split()[0], "%Y-%m-%d").date()


def _readdatetime(timestring):
    """Get a datetime object from a Gnucash datetime string.

    Arguments:
        timestring -- String representing a datetime.
    Example:
        >>> _readdatetime("2002-12-01 11:22:33 +0100")
        datetime.datetime(2002, 12, 1, 11, 22, 33)

    """
    if timestring is None:
        return None
    return datetime.datetime.strptime(timestring.rsplit(None, 1)[0],
                                      "%Y-%m-%d %H:%M:%S")


def _currencyformatting(val, uselocale=True, precision=None, dashsymb=None):
    """Format a currency value.

    Arguments:
        val       -- The value to format, must be convertible to Decimal.
        uselocale -- Format the number using the locale setting.
        precision -- Used decimal precision (only unless uselocale).
        dashsymb  -- Replace a zero fractional part if dashsymb is not None,
            only used if uselocale. Example: '12.00' -> '12,-'.
    Examples:
        >>> _currencyformatting(Decimal("12.34567"), uselocale=False,
        ...     precision=3)
        '12.346'

    """
    val = Decimal(val)
    if precision is not None:
        prec = Decimal(10) ** -precision
        val = val.quantize(prec)
    if uselocale:
        val = locale.currency(val, symbol=False, grouping=True)
        if dashsymb is not None:
            dp = locale.localeconv()['mon_decimal_point']
            parts = val.rsplit(dp, 2)
            try:
                if len(parts) == 1:
                    val = '%s%s%s' % (val, dp, dashsymb)
                elif not int(parts[1]):
                    val = '%s%s%s' % (parts[0], dp, dashsymb)
            except:
                pass
    return str(val)


def _quantityformatting(val, uselocale=True, precision=None, dashsymb=None):
    """Format a quantity value.

    Arguments:
        val       -- The value to format, must be convertible to Decimal.
        uselocale -- Format the number using the locale setting.
        precision -- Used decimal precision (only unless uselocale).
        dashsymb  -- Replace a zero fractional part if dashsymb is not None,
            only used if uselocale. Example: '12.00' -> '12,-'.
    Examples:
        >>> _quantityformatting(Decimal("12.34567"), uselocale=False,
        ...     precision=3)
        '12.346'

    """
    val = Decimal(val)
    if precision is not None:
        prec = Decimal(10) ** -precision
        val = val.quantize(prec)
    if uselocale:
        val = locale.format("%.12g", val, grouping=True, monetary=False)
        if dashsymb is not None:
            dp = locale.localeconv()['decimal_point']
            parts = val.rsplit(dp, 2)
            try:
                if len(parts) == 1:
                    val = '%s%s%s' % (val, dp, dashsymb)
                elif not int(parts[1]):
                    val = '%s%s%s' % (parts[0], dp, dashsymb)
            except:
                pass
    return str(val)


def intid(id):
    """Convert id to an integer, if possible.

    Else id is returned unchanged. This is used to access ids in
    Gnucash data files easier. The ids are often integers.

    Example:
        >>> intid(None) is None
        True
        >>> intid(5)
        5
        >>> intid('0012')
        12
        >>> # Because the doctest for this call expects unicode string
        >>> # results, it does not work simultaneously on Python2 and Python3.
        >>> # Therfore we skip it for now and added an equivalent test method
        >>> # testIntid in test.py.
        >>> intid('abc') # doctest: +SKIP
            'abc'

    """
    try:
        id2 = int(id)
    except Exception:
        id2 = id
    return id2


class _MyTemplate(Template):
    idpattern = '[_a-z][-_a-z0-9]*'


# Things if the module is run as script

def createInvoice(invoiceid, template=None, outfile=None, options=None):

    """Create an invoice from a Gnucash data file.

    Arguments:
        invoiceid -- id of the invoice.
        template   -- name of the invoice template file, or list of lines.
        outfile    -- File name for the generated invoice, default is stdout.
        options    -- object holding options, see methods of Gcinvoice for used
            options.

    """
    gc = Gcinvoice(options=options)
    gc.parse()
    gc.createInvoice(invoiceid, template=template, outfile=outfile)


if __name__ == '__main__':
    description = textwrap.dedent("""\
        gcinvoice.py extracts customer and invoice data from a Gnucash
        data file and uses a template to generate an invoice.
        """)
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('invoiceid', help='The invoice ID')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument("-d", "--debug", action="store_true", dest="debug")
    parser.add_argument("-c", "--config", dest="config", metavar='FILE',
                        help="read configuration from FILE")
    parser.add_argument("-g", "--gcfile", dest="gcfile", metavar='FILE',
                        help="use Gnucash data file FILE")
    parser.add_argument("-t", "--template", dest="template", metavar='FILE',
                        help="use template FILE")
    parser.add_argument("-o", "--outfile", dest="outfile", metavar='FILE',
                        help="use FILE for output instead of stdout")
    args = parser.parse_args()
    if args.debug:
        args.loglevel = logging.DEBUG

    template = str(args.template) if args.template else None

    createInvoice(args.invoiceid, template=template,
                  outfile=getattr(args, 'outfile', None), options=args)
