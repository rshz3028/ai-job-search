# Build a part-time CV variant from cv/main_parttime_fr.json with qualities/skills tailored to a job type.
# Usage: python tools/parttime_cv.py <Slug>:<caisse|stock|resto|vente|service> ...  -> cv/Rishikesh_Sudheer_CV_<Slug>.pdf
import json,copy,subprocess,sys,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOWN=json.load(open(os.path.join(ROOT,'profile.local.json'),encoding='utf-8'))['location'].split(',')[0].strip()
os.chdir(os.path.join(ROOT,'cv'))
base=json.load(open('main_parttime_fr.json',encoding='utf-8'))
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
}
def make(slug,kind,extra_head=None):
    v=V[kind]; c=copy.deepcopy(base)
    c['headline']=extra_head or v['head']
    c['sidebar'][0]['bullets']=v['skills']
    c['sidebar'][2]['bullets']=v['qual']
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
    import shutil; shutil.copy(f+'.pdf',out)
    print(slug,[l for l in pages.splitlines() if l.startswith('Pages')],out)
for a in sys.argv[1:]:
    s,k=a.split(':'); make(s,k)
