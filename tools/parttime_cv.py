# Build a part-time CV variant with qualities/skills tailored to a job type.
# Usage: python tools/parttime_cv.py <Slug>:<kind>[:<custom headline>] ...  -> cv/Rishikesh_Sudheer_CV_<Slug>.pdf
#   French kinds (cv/main_parttime_fr.json): caisse | stock | resto | vente | service
#   English hotel kinds (cv/main_parttime_en.json, for English-speaking hotels in Paris):
#     hotel (day/weekend reception) | hotel_night (night receptionist) | hotel_service (room service, guest services)
#   Hotel kinds put the hotel job first under "Hospitality and Customer Service", then "Other Experience".
import json,copy,subprocess,sys,os,shutil
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOWN=json.load(open(os.path.join(ROOT,'profile.local.json'),encoding='utf-8'))['location'].split(',')[0].strip()
os.chdir(os.path.join(ROOT,'cv'))
base=json.load(open('main_parttime_fr.json',encoding='utf-8'))
base_en=json.load(open('main_parttime_en.json',encoding='utf-8'))
G=base['sections'][1]['entries'][0]['bullets']  # caisse, accueil, réception, propreté
V={
 'caisse':dict(head="Étudiant international — hôte de caisse, temps partiel",
   skills=["Tenue de caisse (espèces, carte)","Accueil et conseil client","Encaissement et rendu de monnaie","Mise en rayon et rangement","Outils informatiques (Excel, Word)"],
   qual=["Souriant et à l'écoute des clients","Rigoureux et honnête avec l'argent","Rapide et précis aux heures de pointe","Fiable et ponctuel"],
   prof="Expérience en supermarché à la caisse : encaissement en espèces et par carte, accueil des clients et aide pour trouver les produits.", order=[0,1,2,3]),
 'stock':dict(head="Étudiant international — préparation de commandes, stock et mise en rayon",
   skills=["Préparation et contrôle des commandes","Réception, stock, mise en rayon","Déchargement des livraisons","Propreté, hygiène et sécurité","Tenue de caisse, accueil client"],
   qual=["Organisé et méthodique","Précis, attentif aux détails","Résistant au travail physique","Fiable et ponctuel"],
   prof="Expérience en supermarché : réception des livraisons, gestion du stock, mise en rayon quotidienne, mais aussi caisse et aide aux clients.", order=[2,3,0,1]),
 'resto':dict(head="Étudiant international — équipier polyvalent restauration",
   skills=["Accueil et service client","Tenue de caisse (espèces, carte)","Propreté et règles d'hygiène","Réception et mise en place des produits","Travail en équipe"],
   qual=["Dynamique et souriant","Efficace pendant le rush","Rigoureux sur l'hygiène","Fiable et ponctuel"],
   prof="Expérience en supermarché : caisse, accueil des clients, réception et mise en rayon, propreté du magasin. Habitué aux journées rythmées (atelier deux-roues de 9 h à 22 h).", order=[0,1,3,2]),
 'vente':dict(head="Étudiant international — vente et conseil client, temps partiel",
   skills=["Accueil et conseil client","Tenue de caisse (espèces, carte)","Réassort et mise en rayon","Clientèle internationale (anglais bilingue)","Outils informatiques (Excel, Word)"],
   qual=["Souriant et à l'écoute","Bon communicant, explique clairement","Organisé, sens du rangement","Fiable et ponctuel"],
   prof="Expérience en supermarché : accueil des clients, aide pour trouver les produits, caisse, réassort. Bilingue en anglais, à l'aise avec une clientèle internationale.", order=[1,0,2,3]),
 'service':dict(head="Étudiant international — service en salle, temps partiel",
   skills=["Accueil et service client","Mise en place et débarrassage","Propreté et règles d'hygiène","Tenue de caisse","Travail en équipe"],
   qual=["Patient et bienveillant","À l'écoute, bon relationnel","Soigné et organisé","Fiable et ponctuel"],
   prof="Expérience au contact des clients en supermarché (accueil, conseil, caisse) et deux ans de cours particuliers qui m'ont appris la patience et l'écoute.", order=[1,0,3,2]),
 # English hotel variants. hotel_order indexes the hotel bullets (0 check-in/out, 1 calls/emails, 2 room inspections, 3 room service);
 # g20_order indexes the English G20 bullets (0 till, 1 greeting/helping, 2 deliveries/stock, 3 cleaning).
 'hotel':dict(lang='en',head="International student — part-time hotel receptionist (English-speaking)",
   skills=["Guest check-in and check-out","Reservations by phone and email","Room inspections and room service","Cash and card payments","Computer tools (Excel, Word, email)"],
   qual=["Friendly and welcoming","Calm and patient with guests","Works well under pressure","Reliable and punctual"],
   prof="Hotel front-desk experience in India: checking guests in and out, logging stays in the hotel system, handling reservation calls and guest emails, inspecting rooms and delivering room service. Customer service and cash and card payments at a Paris-area supermarket. Fluent in English (C1) and at ease with international guests. Reliable, punctual and quick to learn.",
   hotel_order=[0,1,2,3], g20_order=[1,0,3]),
 'hotel_night':dict(lang='en',head="International student — part-time night receptionist (English-speaking)",
   skills=["Guest check-in and check-out","Reservations by phone and email","Logging stays in the hotel system","Cash and card payments","Computer tools (Excel, Word, email)"],
   qual=["Comfortable on night shifts","Calm and patient with guests","Reliable and punctual","Friendly and welcoming"],
   prof="Hotel front-desk experience in India: checking guests in and out, logging each stay in the hotel system, answering reservation calls and guest emails, and inspecting rooms before arrivals. Customer service and cash and card payments at a Paris-area supermarket. Fluent in English (C1), at ease with international guests, and calm and dependable on night shifts.",
   hotel_order=[0,1,2,3], g20_order=[1,0,3]),
 'hotel_service':dict(lang='en',head="International student — part-time hotel guest services and room service (English-speaking)",
   skills=["Room service for guests","Room inspections before check-in","Guest check-in and check-out","Keeping spaces clean and tidy","Cash and card payments"],
   qual=["Friendly and welcoming","Attentive to detail and cleanliness","Comfortable with physical work","Reliable and punctual"],
   prof="Hotel experience in India: room service, room inspections after check-out and before check-in, guest check-in and check-out, and reservation calls. Customer service, cleaning and restocking at a Paris-area supermarket. Fluent in English (C1) and at ease with international guests. Reliable, punctual and quick to learn.",
   hotel_order=[3,2,0,1], g20_order=[1,3,0]),
}
EN_PROFILE_START="International Master's student in Paris (ESIGELEC), available immediately for a part-time job of up to 20 hours a week, including evenings, nights and weekends. "
def hotel_sections(c,v):
    ents=c['sections'][1]['entries']
    pick=lambda key: next(e for e in ents if key in e['title'])
    hotel,g20,moto,tutor=pick('Hotel'),pick('G20'),pick('Motorolf'),pick('Tutor')
    hotel['bullets']=[hotel['bullets'][i] for i in v['hotel_order']]
    g20['bullets']=[g20['bullets'][i] for i in v['g20_order']]
    moto['bullets']=moto['bullets'][1:]  # keep pace + safety, drop the mechanical detail
    c['sections'][1]={'heading':'Hospitality and Customer Service','entries':[hotel,g20]}
    c['sections'].insert(2,{'heading':'Other Experience','entries':[moto,tutor]})
def make(slug,kind,extra_head=None):
    v=V[kind]; en=v.get('lang')=='en'; c=copy.deepcopy(base_en if en else base)
    c['headline']=extra_head or v['head']
    c['sidebar'][0]['bullets']=v['skills']
    c['sidebar'][2]['bullets']=v['qual']
    if en:
        c['sections'][0]['text']=EN_PROFILE_START+v['prof']
        if 'hotel_order' in v: hotel_sections(c,v)
    else:
        c['sections'][0]['text']=("Étudiant international en Master à l'ESIGELEC, installé à "+TOWN+", disponible immédiatement pour un emploi à temps partiel (jusqu'à 20 h par semaine), y compris le soir et le week-end. "+v['prof']+("" if "nglais" in v['prof'] else " Bilingue en anglais."))
        c['sections'][1]['entries'][0]['bullets']=[G[i] for i in v['order']]
    f=f'pt_{slug}'
    json.dump(c,open(f+'.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
    for p in (f+'.pdf',f+'.docx'):
        if os.path.exists(p): os.remove(p)
    subprocess.run(['node','../templates/cv/rishi-sidebar/build.js',f+'.json'],check=True,capture_output=True)
    subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','../templates/cv/rishi-sidebar/docx2pdf.ps1',f+'.docx'],check=True,capture_output=True)
    pages=subprocess.run(['pdfinfo',f+'.pdf'],capture_output=True,text=True).stdout
    out=f'Rishikesh_Sudheer_CV_{slug}.pdf'
    shutil.copy(f+'.pdf',out)
    print(slug,[l for l in pages.splitlines() if l.startswith('Pages')],out)
for a in sys.argv[1:]:
    parts=a.split(':',2); make(parts[0],parts[1],parts[2] if len(parts)>2 else None)
