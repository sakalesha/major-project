import os, warnings, json
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, matplotlib.pyplot as plt, joblib
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report, confusion_matrix
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import AdaBoostClassifier, BaggingClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.linear_model import RidgeClassifier, SGDClassifier, PassiveAggressiveClassifier, Perceptron
SEED=42; DATA_PATH='NiftyEvent50_final.csv'; OUT='outputs'; MD='models'
os.makedirs(OUT,exist_ok=True); os.makedirs(MD,exist_ok=True)
df=pd.read_csv(DATA_PATH); required=['date','ticker','sector','event_type','pre_event_price','volatility_label','direction_label','is_primary_filing']
missing=[c for c in required if c not in df]
if missing: raise ValueError(f'Missing columns: {missing}')
df['date']=pd.to_datetime(df['date'],errors='coerce'); df=df.dropna(subset=['date','direction_label','volatility_label']).copy(); df=df.sort_values('date').reset_index(drop=True)
df['year']=df.date.dt.year; df['month']=df.date.dt.month; df['quarter']=df.date.dt.quarter
cat=['ticker','sector','event_type','is_primary_filing']; num=['pre_event_price','year','month','quarter']; features=cat+num
X=df[features]; yd=df.direction_label.astype(str).str.strip().str.title(); yv=df.volatility_label.astype(str).str.strip().str.title()
n=len(df); a=int(.70*n); b=int(.85*n); Xtr,Xv,Xte=X.iloc[:a],X.iloc[a:b],X.iloc[b:]

def prep():
 return ColumnTransformer([('num',Pipeline([('imp',SimpleImputer(strategy='median')),('scale',StandardScaler())]),num),('cat',Pipeline([('imp',SimpleImputer(strategy='most_frequent')),('oh',OneHotEncoder(handle_unknown='ignore'))]),cat)])
def models():
 return {'Decision Tree':DecisionTreeClassifier(max_depth=8,min_samples_leaf=5,class_weight='balanced',random_state=SEED),'AdaBoost':AdaBoostClassifier(n_estimators=100,learning_rate=.5,random_state=SEED),'Bagging':BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=6,random_state=SEED),n_estimators=60,random_state=SEED,n_jobs=-1),'Gaussian Naive Bayes':GaussianNB(),'Linear Discriminant Analysis':LinearDiscriminantAnalysis(),'Quadratic Discriminant Analysis':QuadraticDiscriminantAnalysis(reg_param=.2),'Ridge Classifier':RidgeClassifier(class_weight='balanced'),'SGD Classifier':SGDClassifier(loss='log_loss',max_iter=3000,tol=1e-3,class_weight='balanced',random_state=SEED),'Perceptron':Perceptron(max_iter=3000,class_weight='balanced',random_state=SEED),'Passive Aggressive':PassiveAggressiveClassifier(max_iter=3000,tol=1e-3,class_weight='balanced',random_state=SEED)}
def run(task,y):
 yt,yval,ytest=y.iloc[:a],y.iloc[a:b],y.iloc[b:]; rows=[]; fitted={}
 for name,est in models().items():
  print(f'[{task}] {name}')
  try:
   p=Pipeline([('preprocess',prep()),('model',clone(est))]); p.fit(Xtr,yt); pred=p.predict(Xv)
   rows.append({'Model':name,'Accuracy':accuracy_score(yval,pred),'Precision_macro':precision_score(yval,pred,average='macro',zero_division=0),'Recall_macro':recall_score(yval,pred,average='macro',zero_division=0),'F1_macro':f1_score(yval,pred,average='macro',zero_division=0)}); fitted[name]=p
  except Exception as e: print('FAILED',name,repr(e))
 res=pd.DataFrame(rows).sort_values('F1_macro',ascending=False); res.to_csv(f'{OUT}/{task.lower()}_validation_comparison.csv',index=False)
 if res.empty: raise RuntimeError(f'All models failed for {task}')
 bestname=res.iloc[0].Model; best=fitted[bestname]; best.fit(pd.concat([Xtr,Xv]),pd.concat([yt,yval])); pred=best.predict(Xte)
 cm=confusion_matrix(ytest,pred,labels=best.classes_); pd.DataFrame(cm,index=best.classes_,columns=best.classes_).to_csv(f'{OUT}/{task.lower()}_test_confusion_matrix.csv')
 pd.DataFrame(classification_report(ytest,pred,output_dict=True,zero_division=0)).transpose().to_csv(f'{OUT}/{task.lower()}_test_classification_report.csv')
 summary={'selected_model':bestname,'test_accuracy':accuracy_score(ytest,pred),'test_macro_f1':f1_score(ytest,pred,average='macro'),'test_precision_macro':precision_score(ytest,pred,average='macro',zero_division=0),'test_recall_macro':recall_score(ytest,pred,average='macro',zero_division=0),'n_test':len(ytest)}
 json.dump(summary,open(f'{OUT}/{task.lower()}_test_summary.json','w'),indent=2); joblib.dump(best,f'{MD}/{task.lower()}_best_pipeline.joblib')
 plt.figure(figsize=(12,5)); res.set_index('Model')[['Accuracy','F1_macro']].plot(kind='bar'); plt.ylim(0,1); plt.title(f'{task}: 10 additional models (validation)'); plt.tight_layout(); plt.savefig(f'{OUT}/{task.lower()}_model_comparison.png',dpi=150); plt.close()
 plt.figure(figsize=(6,5)); plt.imshow(cm); plt.xticks(range(len(best.classes_)),best.classes_,rotation=45); plt.yticks(range(len(best.classes_)),best.classes_); plt.xlabel('Predicted'); plt.ylabel('Actual'); plt.title(f'{task}: held-out test confusion matrix');
 for i in range(cm.shape[0]):
  for j in range(cm.shape[1]): plt.text(j,i,str(cm[i,j]),ha='center',va='center')
 plt.tight_layout(); plt.savefig(f'{OUT}/{task.lower()}_test_confusion_matrix.png',dpi=150); plt.close()
 print(task,'test metrics:',summary); return res
if __name__=='__main__':
 print('Rows:',n,'Train:',len(Xtr),'Validation:',len(Xv),'Test:',len(Xte)); print('Post-event columns excluded to reduce target leakage.')
 print('\nDirection results'); print(run('Direction',yd).to_string(index=False)); print('\nVolatility results'); print(run('Volatility',yv).to_string(index=False))
