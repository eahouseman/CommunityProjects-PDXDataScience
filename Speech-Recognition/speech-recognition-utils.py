import os
import math
import numpy
#
from scipy.io import wavfile
#
os.putenv('R_USER',"C:\Python36\Lib\site-packages\rpy2")
import rpy2
import rpy2.robjects
#
from rpy2.robjects import Formula
from rpy2.robjects.packages import importr
mgcv = importr("mgcv")

def identityfunction(x):
   out = []
   for i in range(len(x)):
      out.append(x[i])
   return(out)

def absolutevalue(x):
   out = []
   for i in range(len(x)):
      out.append(abs(x[i]))
   return(out)

def difference(x):
   out = []
   for i in range(1,len(x)):
      out.append(x[i]-x[i-1])
   return(out)

def readWaveFiles(dir):
    ff = os.listdir(dir)
    nf = len(ff)
    out = []
    for i in range(nf):
        rate, sound = wavfile.read(dir+'\\'+ff[i])
        data = []
        if sound.dtype=='int16':
            for j in range(len(sound)):
                data.append(sound[j]/32768)
        elif sound.dtype=='int8':
            for j in range(len(sound)):
                data.append(sound[j]/128 - 1)
        else:
            for j in range(len(sound)):
                data.append(sound[j])
        out.append(data)
    return({'data' : out, 'names' : ff})

class Timeseries:
    def __init__(self, data, transform=identityfunction, clip1=500, clip2=500, time=None):
       nx = len(data)
       xs = data[slice(clip1,nx-clip2)]
       if time is None:
           tt = list(range(clip1,nx-clip2))
       else:
           tt = time
       self.time = tt
       self.data = transform(xs)

def getSmoothEnvelope(wvdata, clip1=500, clip2=500):
    ts = Timeseries(wvdata, absolutevalue, clip1, clip2)
    #
    r = rpy2.robjects
    y = r.FloatVector(ts.data)
    x = r.FloatVector(ts.time)
    #
    r.globalenv["y"] = y
    r.globalenv["x"] = x
    #
    ff = Formula("y~s(x)")
    gf = mgcv.gam(ff)
    yhat = numpy.array(r.r.predict(gf))
    #
    return(Timeseries(yhat, clip1=0, clip2=0, time=ts.time))

def plotRawWave(wvdata, transform=identityfunction, clip1=500, clip2=500):
    ts = Timeseries(wvdata, transform, clip1, clip2)
    rpy2.robjects.r.plot(ts.time, ts.data, type='l', xlab='time', ylab='amplitude')

def plotRawWaveAndEnvelope(ts, envelope):
    rpy2.robjects.r.plot(ts.time, ts.data, type='l', xlab='time', ylab='amplitude')
    rpy2.robjects.r.lines(envelope.time, envelope.data, col='red')
    rpy2.robjects.r['dev.flush']()

def closeRPlot():
    rpy2.robjects.r['dev.off']()

def getEnvelopePeakStats(envelope, errorClip=5000):
   # Get time corresponding to maximum envelope
   nx = len(envelope.data)
   x0 = numpy.argsort(envelope.data)[nx-1]
   #
   # If maximum occurs at the beginning, clip some more from the beginning
   if x0==0:
       x0=numpy.argsort(envelope.data[slice(errorClip,nx)])[nx-errorClip-1]+errorClip
   #
   y0 = envelope.data[x0]
   pk = envelope.time[x0]
   #
   d1 = difference(envelope.data)
   d2 = difference(d1)
   a0 = d2[x0-1]
   #
   # Half-width calculated as the difference between peak and x-intercepts
   # of the parabola implied by the 2nd difference and the peak height
   halfwidth = math.sqrt(-y0/a0) 
   return({'peakheight':y0,'peak':pk,'curvature':a0, 'peakwidth':halfwidth})

def getEnvelopePeakStats(envelope, errorClip=5000):
   # Get time corresponding to maximum envelope
   nx = len(envelope.data)
   x0 = numpy.argsort(envelope.data)[nx-1]
   #
   # If maximum occurs at the beginning, clip some more from the beginning
   if x0==0:
       x0=numpy.argsort(envelope.data[slice(errorClip,nx)])[nx-errorClip-1]+errorClip
   #
   y0 = envelope.data[x0]
   pk = envelope.time[x0]
   #
   d1 = difference(envelope.data)
   d2 = difference(d1)
   a0 = d2[x0-1]
   #
   # Half-width calculated as the difference between peak and x-intercepts
   # of the parabola implied by the 2nd difference and the peak height
   halfwidth = math.sqrt(-y0/a0) 
   return({'peakheight':y0,'peak':pk,'curvature':a0, 'peakwidth':halfwidth})

# Weighted Fast-Fourier-Transform (general function)
def FFT(t,x,K=10,L=None,weight=None,ridge=None):
    n = len(t)
    KK = 2*K+1
    if L is None:
        L = float(n)
    if weight is None:
        weight = numpy.repeat(1.0,n)
    tt = []
    h = numpy.repeat(0,KK)
    Bt = numpy.zeros(shape=(KK,n))
    B = numpy.zeros(shape=(n,KK))
    for ti in t:
        tt.append(2.0*numpy.pi*ti/L)
    for i in range(n):
        B[i,K] = 1.0
        Bt[K,i] = weight[i]
    for k in range(K):
          kc = KK-k-1
          h[k] = k-K
          h[kc] = K-k
          for i in range(n):
              B[i,k] = math.sin(float(K-k)*tt[i])
              Bt[k,i] = weight[i]*B[i,k]
              B[i,kc] = math.cos(float(K-k)*tt[i])
              Bt[kc,i] = weight[i]*B[i,kc]
              
    BtB = numpy.matmul(Bt,B)
    Btx = numpy.matmul(Bt,x)
    if ridge is not None:
        for k in range(KK):
            BtB[k,k] = BtB[k,k] + ridge
    #
    coefs = numpy.linalg.solve(BtB,Btx)
    out = {}
    for i in range(KK):
        out[str(h[i])] = coefs[i]
    return(out)  

def getWeightedFFT(ts, mu, sigma, scale, sigmaMult=3, K=10, ridge=1e-6):
    n = len(ts.data)
    x = []
    for y in ts.data:
        x.append(y / scale)
    w = []
    tctr = []
    sigma2 = sigma*sigma
    for t in ts.time:
        tc = t-mu
        tctr.append(tc)
        w.append(tc*tc/2/sigma2)
    mnw = numpy.min(w)
    for i in range(n):
        w[i] = math.exp(mnw-w[i])
    return(FFT(tctr,x,K=K,L=sigmaMult*sigma,weight=w,ridge=ridge))

def indexSet(indx, strv):
    n = len(indx)
    x = []
    for i in range(n):
        x.append(strv[indx[i]])
    ix = numpy.argsort(x)
    #
    curri = 0
    currx = x[ix[0]]
    out = {}
    out[currx]=[indx[ix[0]]]
    for i in range(1,n):
        if x[ix[i]]==currx:
            out[currx].append(indx[ix[i]])
        else:
            curri = curri+1
            currx = x[ix[i]]
            out[currx]=[indx[ix[i]]]
    for k in [*out]:
        out[k].sort()
    return out;

def getMVNStats(dataArray, ndx, ndxRev):
    keys = [*dataArray[0]]
    nFeature = len(keys)
    nObs = len(ndx)
    s = numpy.zeros(shape=(nFeature))
    mu = {}
    Sigma = numpy.zeros(shape=(nFeature,nFeature))
    cs = numpy.zeros(shape=(nFeature,nFeature))
    for j in range(nFeature):
        for i in range(nObs):
            yj = dataArray[ndxRev[ndx[i]]][keys[j]]
            s[j] = s[j]+yj
        mu[keys[j]] = s[j]/nObs
    #
    for i in range(nObs):
        for j in range(nFeature):
            yj = dataArray[ndxRev[ndx[i]]][keys[j]]
            cs[j,j] = cs[j,j] + yj*yj             
            for k in range(j):
                yk = dataArray[ndxRev[ndx[i]]][keys[k]]
                cs[j,k] = cs[j,k] + yj*yk
    for j in range(nFeature):
        Sigma[j,j] = (nObs/(nObs-1))*(cs[j,j]/nObs - mu[keys[j]]*mu[keys[j]])
        for k in range(j):
            Sigma[j,k] = (nObs/(nObs-1))*(cs[j,k]/nObs - mu[keys[j]]*mu[keys[k]])
            Sigma[k,j] = Sigma[j,k]
    return({'mu' : mu, 'Sigma': Sigma})

def dmvnorm(x, stat):
    keys = [*x]
    nFeature = len(keys)
    r = numpy.zeros(shape=(nFeature))
    for j in range(nFeature):
        r[j] = x[keys[j]]-stat['mu'][keys[j]]
    rSir = numpy.matmul(r, numpy.linalg.solve(stat['Sigma'],r))
    ldet = numpy.linalg.slogdet(stat['Sigma'])[1]
    lconst = nFeature*math.log(2*math.pi)
    return(-(lconst+ldet+rSir)/2)

def eBayes(x, stats):
   keys = [*stats]
   nFeature = len(keys)
   p = numpy.repeat(0.0,nFeature)
   for j in range(nFeature):
       p[j] = dmvnorm(x, stats[keys[j]])
   mx = numpy.max(p)
   for j in range(nFeature):
       p[j] = math.exp(p[j] - mx)
   out = {}
   for j in range(nFeature):
       out[keys[j]] = p[j]/sum(p)
   return(out)

import rpy2.robjects.numpy2ri
rpy2.robjects.numpy2ri.activate()

def showHeatmap(data,annotation):
  keys = [*data[0]]
  nFeature = len(keys)
  nObs = len(data)
  A = numpy.zeros(shape=(nObs,nFeature))
  for i in range(nObs):
     for j in range(nFeature):
         A[i,j] = data[i][keys[j]]
     
  nr,nc = A.shape
  Ar = rpy2.robjects.r.matrix(A, nrow=nr, ncol=nc)
  #
  cg = numpy.repeat(0.0,255)
  for i in range(255):
     cg[i] = i/255.0
  #
  rpy2.robjects.globalenv["colorgrade"] = rpy2.robjects.FloatVector(cg)
  purples = rpy2.robjects.r.hsv(0.7,cg,1)
  rpy2.robjects.r.heatmap(Ar,scale='n', col=purples, 
    RowSide=rpy2.robjects.StrVector(annotation), 
    labRow=rpy2.robjects.NA_Character)

