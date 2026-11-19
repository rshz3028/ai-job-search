# English part-time CV for tourism / hospitality employers (hostels, hotels, pubs, tours, bookshops).
# Usage: python tools/tourism_cv.py <Slug>:<host|bar|tour|shop> ...  -> cv/Rishikesh_Sudheer_CV_<Slug>.pdf
# Base: cv/pt_GAMIN_en.json (English part-time CV). Only confirmed G20 duties are used.
import json,copy,subprocess,sys,os,shutil
os.chdir(r'D:\dev\ai-job-search-master\cv')
base=json.load(open('pt_GAMIN_en.json',encoding='utf-8'))
LANG="Languages: English (C1, fluent), Hindi, Malayalam, basic French."
V={
 'host':dict(head="International student — guest service and reception, part-time",
   skills=["Welcoming international guests","Answering questions, giving directions","Till / POS: cash and card payments","Keeping public areas clean and tidy","English C1 + Hindi + Malayalam"],
   qual=["Friendly and approachable","Calm and patient with guests","Organised, attentive to detail","Reliable and punctual"],
   prof="Customer-facing experience in a Paris-region supermarket: welcoming customers, answering their questions, cash and card payments and keeping the shop clean and tidy."),
 'bar':dict(head="International student — bar and floor team member, part-time",
   skills=["Welcoming and serving customers","Till / POS: cash and card payments","Receiving deliveries, stock, restocking","Cleaning and hygiene routines","International customers (English C1)"],
   qual=["Friendly, energetic team player","Stays calm during busy service","Organised and quick to learn","Reliable and punctual"],
   prof="Supermarket experience at the till and on the floor: serving customers, cash and card payments, receiving deliveries, restocking and cleaning. Used to long, fast-paced days (workshop shifts from 9am to 10pm)."),
 'tour':dict(head="International student — tourism host and guest assistant, part-time",
   skills=["Welcoming international visitors","Explaining things clearly (tutoring)","Till: cash and card payments","Motorbike and scooter servicing","English C1 + Hindi + Malayalam"],
   qual=["Outgoing, enjoys meeting people","Clear, patient communicator","Adaptable, keeps a cool head","Reliable and punctual"],
   prof="Customer-facing supermarket experience (welcoming customers, answering questions, payments), two years of tutoring that taught me to explain things clearly, and hands-on workshop experience servicing motorbikes and scooters."),
 'shop':dict(head="International student — sales assistant for international customers, part-time",
   skills=["Welcoming and advising customers","Till / POS: cash and card payments","Receiving deliveries, stock, restocking","Keeping the shop tidy and well presented","English C1 + Hindi + Malayalam"],
   qual=["Friendly and approachable","Curious, explains clearly","Organised, attentive to detail","Reliable and punctual"],
   prof="Supermarket experience at the till and on the shop floor: welcoming customers, helping them find products, cash and card payments, receiving deliveries and restocking."),
}
def make(slug,kind):
    v=V[kind]; c=copy.deepcopy(base)
    c['headline']=v['head']; c['sidebar'][0]['bullets']=v['skills']; c['sidebar'][2]['bullets']=v['qual']
    c['sections'][0]['text']=("International Master's student in Paris (ESIGELEC), available immediately for part-time work of up to 20 hours a week, including evenings, nights and weekends. Fluent in English (C1) and at ease with visitors from around the world. "+v['prof']+" Reliable, punctual and quick to learn.")
    f=f'pt_{slug}_en'
    json.dump(c,open(f+'.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
    for p in (f+'.pdf',f+'.docx'):
        if os.path.exists(p): os.remove(p)
    subprocess.run(['node','../templates/cv/rishi-sidebar/build.js',f+'.json'],check=True,capture_output=True)
    subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','../templates/cv/rishi-sidebar/docx2pdf.ps1',f+'.docx'],check=True,capture_output=True)
    pages=subprocess.run(['pdfinfo',f+'.pdf'],capture_output=True,text=True).stdout
    out=f'Rishikesh_Sudheer_CV_{slug}.pdf'; shutil.copy(f+'.pdf',out)
    print(slug,[l for l in pages.splitlines() if l.startswith('Pages')],'cv/'+out)
for a in sys.argv[1:]:
    s,k=a.split(':'); make(s,k)
