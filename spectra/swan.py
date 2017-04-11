"""
Auxiliary class to parse spectra from SWAN ASCII format
"""
import os
import re
import copy
import datetime
import xarray as xr
import numpy as np
from pandas import to_datetime

from attributes import *
from readspec import to_datetime

class Error(Exception):
    pass
  
class SwanSpecFile(object):
    def __init__(self, filename,
                 freqs=None,
                 dirs=None,
                 x=None, y=None,
                 time=False,
                 id='Swan Spectrum',
                 dirorder=False,
                 append=False):
    """
    Read spectra in SWAN ASCII format
    """
        self.times = False
        self.filename = filename
        self.buf = None
        try:
            if freqs is not None:#Writable file
                self.freqs=np.array(freqs)
                self.dirs=np.array(dirs)
                self.x=np.array(x)
                self.y=np.array(y)
                if time:self.times=[]
                self.f=open(filename,'w')
                self.writeHeader(time,id)
                self.fmt=len(self.dirs)*'%4d '
            else:
                self.f=open(filename,'r+' if append else 'r')
                header=self._readhdr('SWAN')
                while True:
                    if not self._readhdr('$'):break
                if self._readhdr('TIME'):
                    self._readhdr('1')
                    self.times=[]
                self.x=[]
                self.y=[]
                for ip in self._readhdr('LONLAT',True):
                    xy=map(float,ip.split())
                    self.x.append(xy[0])
                    self.y.append(xy[1])
                self.x=np.array(self.x)
                self.y=np.array(self.y)
                self.freqs=np.array(map(float,self._readhdr('AFREQ',True)))
                self.dirs=np.array(map(float,self._readhdr('NDIR',True)))
                self._readhdr('QUANT',True)
                self.f.readline()
                self.f.readline()
        except Error as e:
            raise 'File error with %s [%s]' % (filename,e)
        if dirorder:
            self.dirmap=list(np.argsort(self.dirs % 360.))
            self.dirs=self.dirs[self.dirmap] % 360.
        else:
            self.dirmap=False
        lons = np.unique(self.x)
        lats = np.unique(self.y)
        self.is_grid = (len(lons)*len(lats) == len(self.x))
        self.is_site = (len(lons)*len(lats) == 1)

    def _readhdr(self,keyword,numspec=False):
        if not self.buf:self.buf=self.f.readline()
        if self.buf.find(keyword)>=0:
            if numspec:
                line=self.f.readline()
                n=int(line[0:min(len(line),20)])
                self.buf=[self.f.readline() for i in range(0,n)]
            rtn=self.buf
            self.buf=None
        else:
            rtn=False
        return rtn

    def read(self):
        if not self.f:return None
        if isinstance(self.times,list):
            line=self.f.readline()
            if line:
                ttime=datetime.datetime.strptime(line[0:15],'%Y%m%d.%H%M%S')
                self.times.append(ttime)
            else:
                return None
        Sout=[]
        for ip,pp in enumerate(self.x):
            Snew=np.nan*np.zeros((len(self.freqs),len(self.dirs)))
            if self._readhdr('NODATA'):
                pass
            else:
                if self._readhdr('ZERO'):
                    Snew=np.zeros((len(self.f),len(self.dirs)))
                elif self._readhdr('FACTOR'):
                    fac=float(self.f.readline())
                    for i,f in enumerate(self.freqs):
                        line=self.f.readline()
                        lsplit=line.split()
                        try:
                            Snew[i,:]=map(float,lsplit)
                        except:
                            pass
                    Snew*=fac
                    if self.dirmap:
                        Snew=Snew[:,self.dirmap]
            Sout.append(Snew)
        return Sout

    def scan(self,time):
        nf=len(self.S.freqs)+1
        tstr=time.strftime('%Y%m%d.%H%M%S')
        i=0
        while True:
            line=self.f.readline()
            if not line:
                return -1
            elif line[:15]==tstr:
                self.f.seek(-len(line),1)
                return i/nf
            i+=1

    def readall(self):
        while True:
            sset=self.read()
            if sset:
                yield sset
            else:
                break
            
    def writeHeader(self,time=False,str1='',str2=''):
        strout='SWAN   1\n$   '+str1+'\n$   '+str2+'\n'
        if (time):strout+='TIME\n1\n'
        np=len(self.x)
        strout+='LONLAT\n'+str(np)+'\n'
        for i,loc in enumerate(self.x):
            strout+='%f %f\n' % (loc,self.y[i])
        strout += 'AFREQ\n%d\n' % (len(self.freqs))
        for freq in self.freqs:strout+='%f\n' % (freq)
        
        strout+='NDIR\n%d\n' % (len(self.dirs))
        for dir in self.dirs:strout+='%f\n' % (dir)  
        
        strout+='QUANT\n1\nVaDens\nm2/Hz/degr\n-99\tException value\n'
        self.f.write(strout)
    
    def writeSpectra(self,specarray):
        for S in specarray:
            fac = S.max()/9998.
            if fac==np.nan:
                strout='NODATA\n'
            elif fac<=0:
                strout='ZERO\n'
            else:
                strout='FACTOR\n'+str(fac)+'\n'
                for row in S:
                    strout+=(self.fmt % tuple(row/fac)) + '\n'
            self.f.write(strout)
            
            
    def readSpectrum(self):
        if self.S.any():
            fac = self.S.max()/9998
            if fac<0:return 'NODATA\n'
            strout='FACTOR\n'+str(fac)+'\n'
            for row in self.S:
                strout+=(self.fmt % tuple(row/fac)) + '\n'
            return strout
        else:
            return 'NODATA\n'

    def readTable(self,headers=['X-wsp','Y-wsp','dep']):
        """
        Read SWAN tab file for extracting wind parameters
        """
        fileroot=os.path.splitext(self.filename)[0]
        try:
            with open(fileroot+'.tab') as f:
                for i in range(0,6):
                    hline=f.readline()
                    if i==3:
                        hline=f.readline()
                        bits=re.split("\s+",hline)
                        hind=[bits.index(h)-1 if h in bits else -1 for h in headers]
                ttime=[]
                dep=[]
                uwnd=[]
                vwnd=[]
                for line in f.readlines():
                    ttime.append(datetime.datetime.strptime(line[0:15],'%Y%m%d.%H%M%S'))
                    bits=re.split('\s+',line)
                    if hind[0]>0:uwnd.append(float(bits[hind[0]]))
                    if hind[1]>0:vwnd.append(float(bits[hind[1]]))
                    if hind[2]>0:dep.append(float(bits[hind[2]]))
            return ttime,uwnd,vwnd,dep
        except Exception as e:
            print str(e)
            return None

    def close(self):
        if self.f:self.f.close()
        self.f=False    